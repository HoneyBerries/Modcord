package net.honeyberries.action;

import net.dv8tion.jda.api.JDA;
import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.Member;
import net.dv8tion.jda.api.entities.User;
import net.dv8tion.jda.api.entities.channel.Channel;
import net.dv8tion.jda.api.entities.channel.middleman.MessageChannel;
import net.dv8tion.jda.api.exceptions.InsufficientPermissionException;
import net.dv8tion.jda.api.exceptions.ErrorResponseException;
import net.dv8tion.jda.api.requests.ErrorResponse;
import net.dv8tion.jda.api.utils.messages.MessageCreateData;
import net.dv8tion.jda.api.entities.UserSnowflake;
import net.honeyberries.config.AppConfig;
import net.honeyberries.database.repository.GuildModerationActionsRepository;
import net.honeyberries.database.repository.GuildPreferencesRepository;
import net.honeyberries.database.Database;
import net.honeyberries.datatypes.action.ActionData;
import net.honeyberries.datatypes.action.ActionType;
import net.honeyberries.datatypes.action.MessageDeletion;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.preferences.GuildPreferences;
import net.honeyberries.discord.JDAManager;
import net.honeyberries.timeout.RateLimiter;
import net.honeyberries.ui.ActionEmbedUI;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.time.Duration;
import java.util.List;
import java.util.Objects;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

/**
 * Executes moderation actions against guild members and messages.
 * Handles the full lifecycle of an action: user notification, message deletions, moderation application, and audit logging.
 * Gracefully handles Discord permission failures and partial success scenarios.
 * <p>
 * A per-guild {@link RateLimiter} caps moderation actions to 20 per 10 seconds,
 * protecting against runaway AI responses that could apply hundreds of actions in a burst.
 */
public class ActionHandler {

    /** Singleton instance. */
    @NotNull
    private static final ActionHandler INSTANCE = new ActionHandler();
    /** Logger for action execution and failures. */
    private final Logger logger = LoggerFactory.getLogger(ActionHandler.class);
    /** JDA client for Discord API calls. */
    @NotNull
    private final JDA jda = JDAManager.getInstance().getJDA();

    /**
     * Per-guild rate limiter: maximum 20 actions in a 10-second window.
     * Prevents an unexpected AI response from banning an entire server at once.
     */
    private final RateLimiter<GuildID> rateLimiter = new RateLimiter<>(20, 10, TimeUnit.SECONDS);

    private ActionHandler() {}

    /**
     * Retrieves the singleton instance of this action handler.
     *
     * @return the singleton {@code ActionHandler}
     */
    public static ActionHandler getInstance() {
        return INSTANCE;
    }

    /**
     * Processes a moderation action against a target user in a guild.
     * Executes the following steps in order:
     * <ol>
     *   <li>Checks the per-guild rate limit; rejects with a warning if exceeded</li>
     *   <li>Notifies the target user via DM (before action, so they still share guild with bot)</li>
     *   <li>Deletes flagged messages from channels</li>
     *   <li>Applies the moderation action (timeout, kick, ban, etc.)</li>
     *   <li>Posts an audit log entry to the designated audit channel (after action, to reflect success)</li>
     * </ol>
     *
     * @param actionData the moderation action to process
     * @return {@code true} if both moderation action and all message deletions succeeded; {@code false} if guild not found, rate-limited, or action failed
     * @throws NullPointerException if {@code actionData} is {@code null}
     */
    public boolean processAction(@NotNull ActionData actionData) {
        Objects.requireNonNull(actionData, "actionData must not be null");
        Guild guild = jda.getGuildById(actionData.guildId().value());
        if (guild == null) {
            logger.warn("Cannot process action {}: guild {} not found", actionData.id(), actionData.guildId());
            return false;
        }

        if (!rateLimiter.tryAcquire(actionData.guildId())) {
            logger.warn("Rate limit exceeded for guild {} — dropping action {} ({})",
                    actionData.guildId(), actionData.id(), actionData.action());
            return false;
        }

        sendUserDmBestEffort(guild, actionData);
        boolean deletionsApplied = applyMessageDeletions(guild, actionData);
        boolean actionApplied = applyModerationAction(guild, actionData);

        if (actionApplied) {
            sendAuditLogBestEffort(guild, actionData);
        }

        return actionApplied && deletionsApplied;
    }

    /**
     * Reverts a previously applied moderation action.
     * <p>
     * Rolls back BAN → issues unban; TIMEOUT → removes timeout; KICK and WARN have no automated
     * reversal (they are logged only). Records the reversal in {@code guild_moderation_action_reversals}.
     *
     * @param actionId the UUID of the action to revert, must not be {@code null}
     * @param reason   reason for the reversal, displayed in the audit embed, must not be {@code null}
     * @return {@code true} if the reversal was applied or is not applicable; {@code false} on error
     * @throws NullPointerException if {@code actionId} or {@code reason} is {@code null}
     */
    public boolean rollbackAction(@NotNull UUID actionId, @NotNull String reason) {
        Objects.requireNonNull(actionId, "actionId must not be null");
        Objects.requireNonNull(reason, "reason must not be null");

        ActionData action = GuildModerationActionsRepository.getInstance().getActionById(actionId);
        if (action == null) {
            logger.warn("Cannot rollback action {}: not found in database", actionId);
            return false;
        }

        Guild guild = jda.getGuildById(action.guildId().value());
        if (guild == null) {
            logger.warn("Cannot rollback action {}: guild {} not found", actionId, action.guildId());
            return false;
        }

        boolean rolled = switch (action.action()) {
            case BAN -> {
                try {
                    guild.unban(UserSnowflake.fromId(action.userId().value()))
                            .reason("Rollback of action " + actionId + ": " + reason)
                            .timeout(AppConfig.getInstance().getDiscordRequestTimeout(), TimeUnit.SECONDS)
                            .complete();
                    yield true;
                } catch (Exception e) {
                    logger.warn("Failed to unban user {} for rollback of action {}", action.userId(), actionId, e);
                    yield false;
                }
            }
            case TIMEOUT -> {
                try {
                    Member member = guild.retrieveMemberById(action.userId().value())
                            .timeout(AppConfig.getInstance().getDiscordRequestTimeout(), TimeUnit.SECONDS)
                            .complete();
                    if (member == null) {
                        logger.warn("Cannot remove timeout for rollback of action {}: member not found", actionId);
                        yield false;
                    }
                    member.removeTimeout().reason("Rollback of action " + actionId + ": " + reason)
                            .timeout(AppConfig.getInstance().getDiscordRequestTimeout(), TimeUnit.SECONDS)
                            .complete();
                    yield true;
                } catch (Exception e) {
                    logger.warn("Failed to remove timeout for rollback of action {}", actionId, e);
                    yield false;
                }
            }
            // KICK/WARN/DELETE/UNBAN/NULL have no automated reversal
            default -> {
                logger.info("Action {} ({}) has no automated reversal — marking as rolled back", actionId, action.action());
                yield true;
            }
        };

        if (rolled) {
            GuildModerationActionsRepository.getInstance().recordReversal(actionId, reason);
        }

        return rolled;
    }



    /**
     * Deletes all flagged messages from the guild, logging failures per message.
     *
     * @param guild      the guild containing the messages
     * @param actionData the action specifying messages to delete
     * @return {@code true} if all deletions succeeded; {@code false} if any deletion failed
     */
    private boolean applyMessageDeletions(@NotNull Guild guild, @NotNull ActionData actionData) {
        Objects.requireNonNull(guild, "guild must not be null");
        Objects.requireNonNull(actionData, "actionData must not be null");
        boolean success = true;

        for (MessageDeletion deletion : actionData.deletions()) {
            Channel channel = guild.getGuildChannelById(deletion.channelId().value());
            if (!(channel instanceof MessageChannel messageChannel)) {
                logger.warn(
                        "Failed to delete message {} in guild {}: channel {} is null or not message-capable",
                        deletion.messageId(), guild.getId(), deletion.channelId()
                );
                success = false;
                continue;
            }

            try {
                messageChannel.deleteMessageById(deletion.messageId().value()).complete();
            } catch (ErrorResponseException e) {
                if (e.getErrorResponse() == ErrorResponse.UNKNOWN_MESSAGE) {
                    logger.debug("Message {} already deleted in channel {} — skipping", deletion.messageId(), deletion.channelId());
                } else {
                    logActionFailure("delete message " + deletion.messageId(), actionData, guild, e);
                    success = false;
                }
            } catch (Exception e) {
                logActionFailure("delete message " + deletion.messageId(), actionData, guild, e);
                success = false;
            }
        }

        return success;
    }

    /**
     * Applies the moderation action (timeout, kick, ban, etc.) to the target user.
     * Dispatches to type-specific handlers based on the action type.
     *
     * @param guild      the guild to apply the action in
     * @param actionData the action details
     * @return {@code true} if the action succeeded; {@code false} if it failed or was skipped
     */
    private boolean applyModerationAction(@NotNull Guild guild, @NotNull ActionData actionData) {
        Objects.requireNonNull(guild, "guild must not be null");
        Objects.requireNonNull(actionData, "actionData must not be null");
        try {
            return switch (actionData.action()) {
                case NULL, DELETE, WARN -> true;
                case TIMEOUT -> applyTimeout(guild, actionData);
                case KICK    -> applyKick(guild, actionData);
                case BAN     -> applyBan(guild, actionData);
                case UNBAN   -> applyUnban(guild, actionData);
            };
        } catch (Exception e) {
            logActionFailure(
                    actionData.action().name().toLowerCase() + " user " + actionData.userId().value(),
                    actionData, guild, e
            );
            return false;
        }
    }



    /**
     * Applies a timeout to the target user for the specified duration.
     *
     * @param guild      the guild to apply the timeout in
     * @param actionData the action specifying timeout duration
     * @return {@code true} if the timeout succeeded; {@code false} if member not found or duration invalid
     */
    private boolean applyTimeout(@NotNull Guild guild, @NotNull ActionData actionData) {
        Objects.requireNonNull(guild, "guild must not be null");
        Objects.requireNonNull(actionData, "actionData must not be null");
        Member member = guild.retrieveMemberById(actionData.userId().value()).complete();
        if (member == null) {
            logger.warn("Failed to timeout user {} in guild {}: member not found",
                    actionData.userId(), guild.getId());
            return false;
        }

        long timeoutSeconds = actionData.timeoutDuration();
        if (timeoutSeconds <= 0) {
            logger.warn("Failed to timeout user {} in guild {}: invalid timeout duration {}",
                    actionData.userId(), guild.getId(), timeoutSeconds);
            return false;
        }

        member.timeoutFor(Duration.ofSeconds(timeoutSeconds))
                .reason(actionData.reason())
                .complete();
        return true;
    }

    /**
     * Kicks the target user from the guild.
     *
     * @param guild      the guild to kick the user from
     * @param actionData the action specifying the user and reason
     * @return {@code true} if the kick succeeded; {@code false} if member not found
     */
    private boolean applyKick(@NotNull Guild guild, @NotNull ActionData actionData) {
        Objects.requireNonNull(guild, "guild must not be null");
        Objects.requireNonNull(actionData, "actionData must not be null");
        Member member = guild.retrieveMemberById(actionData.userId().value()).complete();
        if (member == null) {
            logger.warn("Failed to kick user {} in guild {}: member not found",
                    actionData.userId(), guild.getId());
            return false;
        }

        guild.kick(member)
                .reason(actionData.reason())
                .complete();
        return true;
    }

    /**
     * Bans the target user from the guild.
     *
     * @param guild      the guild to ban the user from
     * @param actionData the action specifying the user and reason
     * @return {@code true} if the ban succeeded
     */
    private boolean applyBan(@NotNull Guild guild, @NotNull ActionData actionData) {
        Objects.requireNonNull(guild, "guild must not be null");
        Objects.requireNonNull(actionData, "actionData must not be null");

        try {
            guild.ban(UserSnowflake.fromId(actionData.userId().value()), 0, TimeUnit.DAYS)
                    .reason(actionData.reason())
                    .complete();
            return true;
        } catch (Exception e) {
            logger.warn("Failed to ban user {}, error: {}", actionData.userId().value(), e.getMessage());
            return false;
        }
    }

    /**
     * Unbans the target user from the guild.
     *
     * @param guild      the guild to unban the user from
     * @param actionData the action specifying the user and reason
     * @return {@code true} if the unban succeeded
     */
    private boolean applyUnban(@NotNull Guild guild, @NotNull ActionData actionData) {
        Objects.requireNonNull(guild, "guild must not be null");
        Objects.requireNonNull(actionData, "actionData must not be null");

        try {
            guild.unban(UserSnowflake.fromId(actionData.userId().value()))
                    .reason(actionData.reason())
                    .complete();
            return true;
        } catch (Exception e) {
            logger.warn("Failed to unban user {}, error: {}", actionData.userId().value(), e.getMessage());
            return false;
        }

    }

    /**
     * Attempts to send a direct message notification to the target user.
     * Must be called BEFORE the moderation action is applied (except for DELETE/WARN actions, which skip DMs).
     * Once a user is kicked or banned, they no longer share a guild with the bot, preventing DM delivery.
     *
     * @param guild      the guild in which the action occurred
     * @param actionData the action to notify about
     */
    private void sendUserDmBestEffort(@NotNull Guild guild, @NotNull ActionData actionData) {
        Objects.requireNonNull(guild, "guild must not be null");
        Objects.requireNonNull(actionData, "actionData must not be null");
        if (actionData.action() == ActionType.NULL || actionData.action() == ActionType.DELETE) {
            return;
        }

        User target = actionData.userId().toUser();
        if (target == null) return;

        MessageCreateData embed = ActionEmbedUI.buildNotificationEmbed(actionData, target);

        try {
            target.openPrivateChannel().complete().sendMessage(embed).complete();
        } catch (Exception e) {
            logger.warn("Failed to DM user {} for action {}", actionData.userId(), actionData.id(), e);
        }
    }

    /**
     * Attempts to post an audit log entry to the guild's designated audit channel.
     * Must be called AFTER the moderation action is applied so the log only reflects actions that actually succeeded.
     * Silently skips if no audit channel is configured or if the database is unavailable.
     *
     * @param guild      the guild in which the action occurred
     * @param actionData the action to audit log
     */
    private void sendAuditLogBestEffort(@NotNull Guild guild, @NotNull ActionData actionData) {
        Objects.requireNonNull(guild, "guild must not be null");
        Objects.requireNonNull(actionData, "actionData must not be null");
        if (actionData.action() == ActionType.NULL || actionData.action() == ActionType.DELETE) {
            return;
        }

        try {
            if (!Database.getInstance().isHealthy()) {
                logger.debug("Skipping audit log for action {} — database unavailable", actionData.id());
                return;
            }

            @Nullable
            GuildPreferences preferences = GuildPreferencesRepository.getInstance()
                    .getGuildPreferences(actionData.guildId());
            if (preferences == null || preferences.auditLogChannelId() == null) {
                return;
            }

            Channel auditChannel = guild.getGuildChannelById(preferences.auditLogChannelId().value());
            if (!(auditChannel instanceof MessageChannel messageChannel)) {
                logger.warn("Audit log channel {} is missing or not message-capable in guild {}",
                        preferences.auditLogChannelId(), guild.getId());
                return;
            }

            User target = actionData.userId().toUser();
            if (target == null) return;

            messageChannel.sendMessage(ActionEmbedUI.buildNotificationEmbed(actionData, target)).complete();
        } catch (Exception e) {
            logger.warn("Failed to post audit embed for action {} in guild {}", actionData.id(), guild.getId(), e);
        }
    }


    /**
     * Returns all actions in a guild that have not yet been reversed.
     * Used by the rollback slash command to present candidates to moderators.
     *
     * @param guildId guild to query, must not be {@code null}
     * @return list of active (non-reversed) actions ordered newest first, never {@code null}
     */
    @NotNull
    public List<ActionData> getActiveActions(@NotNull GuildID guildId) {
        Objects.requireNonNull(guildId, "guildId must not be null");
        return GuildModerationActionsRepository.getInstance().getActiveActions(guildId);
    }

    /**
     * Logs an action failure with appropriate severity based on the error type.
     * Permission failures are logged at WARN level, other failures at ERROR level.
     *
     * @param operation  a description of the operation that failed
     * @param actionData the action that failed
     * @param guild      the guild in which the failure occurred
     * @param e          the exception that caused the failure
     */
    private void logActionFailure(@NotNull String operation, @NotNull ActionData actionData,
                                  @NotNull Guild guild, @NotNull Exception e) {
        Objects.requireNonNull(operation, "operation must not be null");
        Objects.requireNonNull(actionData, "actionData must not be null");
        Objects.requireNonNull(guild, "guild must not be null");
        Objects.requireNonNull(e, "e must not be null");

        if (isPermissionFailure(e)) {
            logger.warn("Permission denied: failed to {} for user {} in guild {} (action={}, moderator={})",
                    operation, actionData.userId(), guild.getId(), actionData.id(), actionData.moderatorId(), e);
            return;
        }

        logger.error("Failed to {} for user {} in guild {} (action={}, moderator={})",
                operation, actionData.userId(), guild.getId(), actionData.id(), actionData.moderatorId(), e);
    }

    /**
     * Determines if an exception represents a permission failure.
     *
     * @param e the exception to check
     * @return {@code true} if the exception indicates insufficient permissions; {@code false} otherwise
     */
    private boolean isPermissionFailure(@NotNull Exception e) {
        Objects.requireNonNull(e, "e must not be null");
        if (e instanceof InsufficientPermissionException) return true;
        if (e instanceof ErrorResponseException err) {
            return err.getErrorResponse() == ErrorResponse.MISSING_PERMISSIONS;
        }
        return false;
    }
}
