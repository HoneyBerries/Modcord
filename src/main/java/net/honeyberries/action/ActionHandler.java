package net.honeyberries.action;

import net.dv8tion.jda.api.EmbedBuilder;
import net.dv8tion.jda.api.JDA;
import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.Member;
import net.dv8tion.jda.api.entities.User;
import net.dv8tion.jda.api.entities.channel.Channel;
import net.dv8tion.jda.api.entities.channel.middleman.MessageChannel;
import net.dv8tion.jda.api.exceptions.InsufficientPermissionException;
import net.dv8tion.jda.api.exceptions.ErrorResponseException;
import net.dv8tion.jda.api.requests.ErrorResponse;
import net.dv8tion.jda.api.utils.TimeFormat;
import net.dv8tion.jda.api.utils.messages.MessageCreateData;
import net.dv8tion.jda.api.utils.messages.MessageCreateBuilder;
import net.dv8tion.jda.api.entities.UserSnowflake;
import net.honeyberries.database.GuildPreferencesRepository;
import net.honeyberries.database.Database;
import net.honeyberries.datatypes.action.ActionData;
import net.honeyberries.datatypes.action.ActionType;
import net.honeyberries.datatypes.action.MessageDeletion;
import net.honeyberries.datatypes.preferences.GuildPreferences;
import net.honeyberries.discord.JDAManager;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.awt.Color;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;
import java.util.concurrent.TimeUnit;

/**
 * Executes moderation actions against guild members and messages.
 * Handles the full lifecycle of an action: user notification, message deletions, moderation application, and audit logging.
 * Gracefully handles Discord permission failures and partial success scenarios.
 */
public class ActionHandler {

    /** Singleton instance. */
    private static final ActionHandler INSTANCE = new ActionHandler();
    /** Logger for action execution and failures. */
    private final Logger logger = LoggerFactory.getLogger(ActionHandler.class);
    /** JDA client for Discord API calls. */
    private final JDA jda = JDAManager.getInstance().getJDA();

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
        Guild guild = jda.getGuildById(actionData.guildId().value());
        if (guild == null) {
            logger.warn("Cannot process action {}: guild {} not found", actionData.id(), actionData.guildId());
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
     * Deletes all flagged messages from the guild, logging failures per message.
     *
     * @param guild the guild containing the messages
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
                        "Failed to delete message {} in guild {}: channel {} unavailable or not message-capable",
                        deletion.messageId(), guild.getId(), deletion.channelId()
                );
                success = false;
                continue;
            }

            try {
                messageChannel.deleteMessageById(deletion.messageId().value()).complete();
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
     * @param guild the guild to apply the action in
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
     * @param guild the guild to apply the timeout in
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
     * @param guild the guild to kick the user from
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
     * @param guild the guild to ban the user from
     * @param actionData the action specifying the user and reason
     * @return {@code true} if the ban succeeded
     */
    private boolean applyBan(@NotNull Guild guild, @NotNull ActionData actionData) {
        Objects.requireNonNull(guild, "guild must not be null");
        Objects.requireNonNull(actionData, "actionData must not be null");
        guild.ban(UserSnowflake.fromId(actionData.userId().value()), 0, TimeUnit.DAYS)
                .reason(actionData.reason())
                .complete();
        return true;
    }

    /**
     * Unbans the target user from the guild.
     *
     * @param guild the guild to unban the user from
     * @param actionData the action specifying the user and reason
     * @return {@code true} if the unban succeeded
     */
    private boolean applyUnban(@NotNull Guild guild, @NotNull ActionData actionData) {
        Objects.requireNonNull(guild, "guild must not be null");
        Objects.requireNonNull(actionData, "actionData must not be null");
        guild.unban(UserSnowflake.fromId(actionData.userId().value()))
                .reason(actionData.reason())
                .complete();
        return true;
    }

    /**
     * Attempts to send a direct message notification to the target user.
     * Must be called BEFORE the moderation action is applied (except for DELETE/WARN actions, which skip DMs).
     * Once a user is kicked or banned, they no longer share a guild with the bot, preventing DM delivery.
     *
     * @param guild the guild in which the action occurred
     * @param actionData the action to notify about
     */
    private void sendUserDmBestEffort(@NotNull Guild guild, @NotNull ActionData actionData) {
        Objects.requireNonNull(guild, "guild must not be null");
        Objects.requireNonNull(actionData, "actionData must not be null");
        if (actionData.action() == ActionType.NULL || actionData.action() == ActionType.DELETE) {
            return;
        }

        User target = resolveUser(actionData, guild);
        if (target == null) return;

        MessageCreateData embed = buildNotificationEmbed(guild, actionData, target);

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
     * @param guild the guild in which the action occurred
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

            User target = resolveUser(actionData, guild);
            if (target == null) return;

            messageChannel.sendMessage(buildNotificationEmbed(guild, actionData, target)).complete();
        } catch (Exception e) {
            logger.warn("Failed to post audit embed for action {} in guild {}", actionData.id(), guild.getId(), e);
        }
    }

    /**
     * Resolves a user by ID from the JDA cache or retrieves it from Discord.
     *
     * @param actionData the action specifying the user ID
     * @param guild the guild for context in error logging
     * @return the resolved {@code User}, or {@code null} if resolution failed
     */
    @Nullable
    private User resolveUser(@NotNull ActionData actionData, @NotNull Guild guild) {
        Objects.requireNonNull(actionData, "actionData must not be null");
        Objects.requireNonNull(guild, "guild must not be null");
        try {
            return jda.retrieveUserById(actionData.userId().value()).complete();
        } catch (Exception e) {
            logger.warn("Failed to resolve user {} for notification in guild {}",
                    actionData.userId(), guild.getId(), e);
            return null;
        }
    }

    /**
     * Constructs a rich embed notification for the action, including user details, moderator, reason, and duration info.
     *
     * @param guild the guild where the action occurred
     * @param actionData the action details
     * @param target the target user of the action
     * @return a {@code MessageCreateData} containing the formatted embed
     */
    @NotNull
    private MessageCreateData buildNotificationEmbed(@NotNull Guild guild, @NotNull ActionData actionData, @NotNull User target) {
        Objects.requireNonNull(guild, "guild must not be null");
        Objects.requireNonNull(actionData, "actionData must not be null");
        Objects.requireNonNull(target, "target must not be null");
        EmbedBuilder embed = new EmbedBuilder()
                .setTitle(actionEmoji(actionData.action()) + " " + actionData.action().name() + " Issued")
                .setColor(actionColor(actionData.action()))
                .setTimestamp(Instant.now())
                .addField("User", "<@" + target.getId() + ">", true)
                .addField("Moderator", "<@" + actionData.moderatorId().value() + ">", true)
                .addField("Reason", actionData.reason(), false)
                .setThumbnail(target.getEffectiveAvatarUrl())
                .setFooter(guild.getName());

        if (actionData.action() == ActionType.TIMEOUT && actionData.timeoutDuration() > 0) {
            Instant expiresAt = Instant.now().plusSeconds(actionData.timeoutDuration());
            embed.addField("Duration",
                    formatDuration(actionData.timeoutDuration()) + " — expires " + TimeFormat.RELATIVE.format(expiresAt),
                    false);
        }

        if (actionData.action() == ActionType.BAN && actionData.banDuration() > 0) {
            if (actionData.banDuration() >= Integer.MAX_VALUE) {
                embed.addField("Duration", "Permanent", false);
            } else {
                Instant expiresAt = Instant.now().plusSeconds(actionData.banDuration());
                embed.addField("Duration",
                        formatDuration(actionData.banDuration()) + " — expires " + TimeFormat.RELATIVE.format(expiresAt),
                        false);
            }
        }

        return new MessageCreateBuilder().setEmbeds(embed.build()).build();
    }

    /**
     * Selects an emoji matching the action type for visual feedback in embeds.
     *
     * @param actionType the moderation action type
     * @return an emoji string representing the action
     */
    @NotNull
    private String actionEmoji(@NotNull ActionType actionType) {
        Objects.requireNonNull(actionType, "actionType must not be null");
        return switch (actionType) {
            case WARN    -> "⚠️";
            case DELETE  -> "🗑️";
            case TIMEOUT -> "⏱️";
            case KICK    -> "👢";
            case BAN     -> "🔨";
            case UNBAN   -> "✅";
            case NULL    -> "⚙️";
        };
    }

    /**
     * Selects a color matching the action type for visual feedback in embeds.
     *
     * @param actionType the moderation action type
     * @return a {@code Color} representing the action severity/type
     */
    @NotNull
    private Color actionColor(@NotNull ActionType actionType) {
        Objects.requireNonNull(actionType, "actionType must not be null");
        return switch (actionType) {
            case WARN            -> Color.YELLOW;
            case DELETE, TIMEOUT -> Color.ORANGE;
            case KICK            -> Color.RED;
            case BAN             -> new Color(139, 0, 0);
            case UNBAN           -> Color.GREEN;
            case NULL            -> Color.GRAY;
        };
    }

    /**
     * Formats a duration in seconds into a human-readable string (e.g., "1d 2h 30m").
     *
     * @param seconds the duration in seconds
     * @return a formatted duration string
     */
    @NotNull
    private String formatDuration(long seconds) {
        long days    = seconds / 86400;
        long hours   = (seconds % 86400) / 3600;
        long minutes = (seconds % 3600) / 60;
        long secs    = seconds % 60;

        StringBuilder sb = new StringBuilder();
        if (days    > 0) sb.append(days).append("d ");
        if (hours   > 0) sb.append(hours).append("h ");
        if (minutes > 0) sb.append(minutes).append("m ");
        if (secs    > 0 || sb.isEmpty()) sb.append(secs).append("s");
        return sb.toString().trim();
    }

    /**
     * Logs an action failure with appropriate severity based on the error type.
     * Permission failures are logged at WARN level, other failures at ERROR level.
     *
     * @param operation a description of the operation that failed
     * @param actionData the action that failed
     * @param guild the guild in which the failure occurred
     * @param e the exception that caused the failure
     */
    private void logActionFailure(@NotNull String operation, @NotNull ActionData actionData, @NotNull Guild guild, @NotNull Exception e) {
        Objects.requireNonNull(operation, "operation must not be null");
        Objects.requireNonNull(actionData, "actionData must not be null");
        Objects.requireNonNull(guild, "guild must not be null");
        Objects.requireNonNull(e, "e must not be null");
        String template = "Failed to {} for user {} in guild {} (actionId={}, moderatorId={})";

        if (isPermissionFailure(e)) {
            logger.warn("Permission denied while trying to " + template.substring(template.indexOf("to ") + 3),
                    operation, actionData.userId(), guild.getId(), actionData.id(), actionData.moderatorId(), e);
            return;
        }

        logger.warn(template, operation, actionData.userId(), guild.getId(),
                actionData.id(), actionData.moderatorId(), e);
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