package net.honeyberries.action;

import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.Member;
import net.dv8tion.jda.api.entities.User;
import net.dv8tion.jda.api.entities.channel.Channel;
import net.dv8tion.jda.api.entities.channel.middleman.MessageChannel;
import net.dv8tion.jda.api.entities.UserSnowflake;
import net.dv8tion.jda.api.exceptions.ErrorResponseException;
import net.dv8tion.jda.api.requests.ErrorResponse;
import net.honeyberries.datatypes.action.ActionData;
import net.honeyberries.datatypes.action.ActionType;
import net.honeyberries.datatypes.action.MessageDeletion;
import net.honeyberries.discord.JDAManager;
import net.honeyberries.services.NotificationService;
import net.honeyberries.ui.ActionEmbedUI;
import net.honeyberries.util.DiscordUtils;
import org.jetbrains.annotations.NotNull;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.TimeUnit;

/**
 * Executes moderation actions against guild members and messages.
 * Handles the full lifecycle of an action: user notification, message deletions, moderation application, and audit logging.
 * Gracefully handles Discord permission failures and partial success scenarios.
 */
public class ActionHandler {

    /** Singleton instance. */
    @NotNull
    private static final ActionHandler INSTANCE = new ActionHandler();
    /** Logger for action execution and failures. */
    private final Logger logger = LoggerFactory.getLogger(ActionHandler.class);
    /** JDA client for Discord API calls. */


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
     * 1. Notifies the target user via DM (before action, so they still share guild with bot)
     * 2. Deletes flagged messages from channels
     * 3. Applies the moderation action (timeout, kick, ban, etc.)
     * 4. Posts an audit log entry to the designated audit channel (after action, to reflect success)
     *
     * @param actionData the moderation action to process
     * @return {@code true} if both moderation action and all message deletions succeeded; {@code false} if guild not found or action failed
     * @throws NullPointerException if {@code actionData} is {@code null}
     */
    public boolean processAction(@NotNull ActionData actionData) {
        Objects.requireNonNull(actionData, "actionData must not be null");
        Guild guild = JDAManager.getInstance().getJDA().getGuildById(actionData.guildId().value());
        if (guild == null) {
            logger.warn("Cannot process action {}: guild {} not found", actionData.id(), actionData.guildId());
            return false;
        }

        sendActionDataToDM(guild, actionData);
        boolean deletionsApplied = applyMessageDeletions(guild, actionData);
        boolean actionApplied = applyModerationAction(guild, actionData);

        if (actionApplied) {
            sendActionDataToAuditLog(guild, actionData);
        }

        return actionApplied && deletionsApplied;
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
    private void sendActionDataToDM(@NotNull Guild guild, @NotNull ActionData actionData) {
        if (actionData.action() == ActionType.NULL) return;

        User target = actionData.userId().toUser();
        if (target == null) return;

        boolean success = NotificationService.getInstance().sendDm(actionData.userId(),
                ActionEmbedUI.buildNotificationEmbed(actionData, target));

        if (!success) {
            logger.warn("Failed to send DM to user {} in guild {}: user not found", actionData.userId(), guild.getId());
        }
    }

    /**
     * Attempts to post an audit log entry to the guild's designated audit channel.
     * Must be called AFTER the moderation action is applied so the log only reflects actions that actually succeeded.
     * Silently skips if no audit channel is configured.
     *
     * @param guild      the guild in which the action occurred
     * @param actionData the action to audit log
     */
    private void sendActionDataToAuditLog(@NotNull Guild guild, @NotNull ActionData actionData) {
        Objects.requireNonNull(guild, "guild must not be null");
        Objects.requireNonNull(actionData, "actionData must not be null");
        if (actionData.action() == ActionType.NULL || actionData.action() == ActionType.DELETE) return;

        User target = actionData.userId().toUser();
        if (target == null) return;

        NotificationService.getInstance().postToAuditChannel(guild,
                ActionEmbedUI.buildNotificationEmbed(actionData, target));
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
    private void logActionFailure(@NotNull String operation, @NotNull ActionData actionData, @NotNull Guild guild, @NotNull Exception e) {
        Objects.requireNonNull(operation, "operation must not be null");
        Objects.requireNonNull(actionData, "actionData must not be null");
        Objects.requireNonNull(guild, "guild must not be null");
        Objects.requireNonNull(e, "e must not be null");

        if (DiscordUtils.isPermissionFailure(e)) {
            logger.warn("Permission denied: failed to {} for user {} in guild {} (action={}, moderator={})",
                    operation, actionData.userId(), guild.getId(), actionData.id(), actionData.moderatorId(), e);
            return;
        }

        logger.error("Failed to {} for user {} in guild {} (action={}, moderator={})",
                operation, actionData.userId(), guild.getId(), actionData.id(), actionData.moderatorId(), e);
    }
}
