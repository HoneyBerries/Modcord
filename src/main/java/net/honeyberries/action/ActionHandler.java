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
import net.honeyberries.datatypes.action.ActionData;
import net.honeyberries.datatypes.action.ActionType;
import net.honeyberries.datatypes.action.MessageDeletion;
import net.honeyberries.datatypes.preferences.GuildPreferences;
import net.honeyberries.discord.JDAManager;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.awt.Color;
import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.TimeUnit;

public class ActionHandler {

    private static final ActionHandler INSTANCE = new ActionHandler();
    private final Logger logger = LoggerFactory.getLogger(ActionHandler.class);
    private final JDA jda = JDAManager.getInstance().getJDA();

    private ActionHandler() {
    }

    public static ActionHandler getInstance() {
        return INSTANCE;
    }

    public boolean processAction(ActionData actionData) {
        Guild guild = jda.getGuildById(actionData.guildId().value());
        if (guild == null) {
            logger.warn("Cannot process action {}: guild {} not found", actionData.id(), actionData.guildId());
            return false;
        }

        boolean deletionsApplied = applyMessageDeletions(guild, actionData);
        boolean actionApplied = applyModerationAction(guild, actionData);

        if (!actionApplied) {
            return false;
        }

        // Notification failures are intentionally non-fatal.
        sendNotificationsBestEffort(guild, actionData);
        return deletionsApplied;
    }

    private boolean applyMessageDeletions(Guild guild, ActionData actionData) {
        boolean success = true;

        for (MessageDeletion deletion : actionData.deletions()) {
            Channel channel = guild.getGuildChannelById(deletion.channelId().value());
            if (!(channel instanceof MessageChannel messageChannel)) {
                logger.warn(
                        "Failed to delete message {} in guild {}: channel {} unavailable or not message-capable",
                        deletion.messageId(),
                        guild.getId(),
                        deletion.channelId()
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

    private boolean applyModerationAction(Guild guild, ActionData actionData) {
        long userId = actionData.userId().value();

        try {
            return switch (actionData.action()) {
                case NULL -> true;
                case DELETE -> true;
                case WARN -> true;
                case TIMEOUT -> applyTimeout(guild, actionData);
                case KICK -> applyKick(guild, actionData);
                case BAN -> applyBan(guild, actionData);
                case UNBAN -> applyUnban(guild, actionData);
            };
        } catch (Exception e) {
            logActionFailure(actionData.action().name().toLowerCase() + " user " + userId, actionData, guild, e);
            return false;
        }
    }

    private boolean applyTimeout(Guild guild, ActionData actionData) {
        Member member = guild.getMemberById(actionData.userId().value());
        if (member == null) {
            logger.warn("Failed to timeout user {} in guild {}: member not found", actionData.userId(), guild.getId());
            return false;
        }

        long timeoutSeconds = actionData.timeoutDuration();
        if (timeoutSeconds <= 0) {
            logger.warn("Failed to timeout user {} in guild {}: invalid timeout duration {}", actionData.userId(), guild.getId(), timeoutSeconds);
            return false;
        }

        member.timeoutFor(Duration.ofSeconds(timeoutSeconds))
                .reason("Modcord: " + actionData.reason())
                .complete();
        return true;
    }

    private boolean applyKick(Guild guild, ActionData actionData) {
        Member member = guild.getMemberById(actionData.userId().value());
        if (member == null) {
            logger.warn("Failed to kick user {} in guild {}: member not found", actionData.userId(), guild.getId());
            return false;
        }

        guild.kick(member)
                .reason("Modcord: " + actionData.reason())
                .complete();
        return true;
    }

    private boolean applyBan(Guild guild, ActionData actionData) {
        guild.ban(UserSnowflake.fromId(actionData.userId().value()), 0, TimeUnit.DAYS)
                .reason("Modcord: " + actionData.reason())
                .complete();
        return true;
    }

    private boolean applyUnban(Guild guild, ActionData actionData) {
        guild.unban(UserSnowflake.fromId(actionData.userId().value()))
                .reason("Modcord: " + actionData.reason())
                .complete();
        return true;
    }

    private void sendNotificationsBestEffort(Guild guild, ActionData actionData) {
        if (actionData.action() == ActionType.NULL || actionData.action() == ActionType.DELETE) {
            return;
        }

        User target;
        try {
            target = jda.retrieveUserById(actionData.userId().value()).complete();
        } catch (Exception e) {
            logger.warn("Failed to resolve user {} for action notification in guild {}", actionData.userId(), guild.getId(), e);
            return;
        }

        MessageCreateData embedMessage = buildNotificationEmbed(guild, actionData, target);

        try {
            target.openPrivateChannel().complete().sendMessage(embedMessage).complete();
        } catch (Exception e) {
            logger.warn("Failed to DM user {} for action {}", actionData.userId(), actionData.id(), e);
        }

        try {
            GuildPreferences preferences = GuildPreferencesRepository.getInstance().getGuildPreferences(actionData.guildId());
            if (preferences == null || preferences.auditLogChannelId() == null) {
                return;
            }

            Channel auditChannel = guild.getGuildChannelById(preferences.auditLogChannelId().value());
            if (auditChannel instanceof MessageChannel messageChannel) {
                messageChannel.sendMessage(embedMessage).complete();
            } else {
                logger.warn("Audit log channel {} is missing or not message-capable in guild {}",
                        preferences.auditLogChannelId(), guild.getId());
            }
        } catch (Exception e) {
            logger.warn("Failed to post audit embed for action {} in guild {}", actionData.id(), guild.getId(), e);
        }
    }

    private MessageCreateData buildNotificationEmbed(Guild guild, ActionData actionData, User target) {
        EmbedBuilder embed = new EmbedBuilder()
                .setTitle(actionEmoji(actionData.action()) + " " + actionData.action().name() + " Issued")
                .setColor(actionColor(actionData.action()))
                .setTimestamp(Instant.now())
                .addField("User", "<@" + target.getId() + ">", true)
                .addField("Moderator", jda.getSelfUser().getAsMention(), true)
                .addField("Reason", actionData.reason(), false)
                .setFooter(guild.getName());

        if (actionData.action() == ActionType.TIMEOUT && actionData.timeoutDuration() > 0) {
            Instant expiresAt = Instant.now().plusSeconds(actionData.timeoutDuration());
            embed.addField("Duration", formatDuration(actionData.timeoutDuration()) + " - expires " + TimeFormat.RELATIVE.format(expiresAt), false);
        }

        if (actionData.action() == ActionType.BAN && actionData.banDuration() > 0) {
            if (actionData.banDuration() >= Integer.MAX_VALUE) {
                embed.addField("Duration", "Permanent", false);
            } else {
                Instant expiresAt = Instant.now().plusSeconds(actionData.banDuration());
                embed.addField("Duration", formatDuration(actionData.banDuration()) + " - expires " + TimeFormat.RELATIVE.format(expiresAt), false);
            }
        }

        return new MessageCreateBuilder().setEmbeds(embed.build()).build();
    }

    private String actionEmoji(ActionType actionType) {
        return switch (actionType) {
            case WARN -> "⚠️";
            case DELETE -> "🗑️";
            case TIMEOUT -> "⏱️";
            case KICK -> "👢";
            case BAN -> "🔨";
            case UNBAN -> "✅";
            case NULL -> "⚙️";
        };
    }

    private Color actionColor(ActionType actionType) {
        return switch (actionType) {
            case WARN -> Color.YELLOW;
            case DELETE, TIMEOUT -> Color.ORANGE;
            case KICK -> Color.RED;
            case BAN -> new Color(139, 0, 0);
            case UNBAN -> Color.GREEN;
            case NULL -> Color.GRAY;
        };
    }

    private String formatDuration(long seconds) {
        long days = seconds / 86400;
        long hours = (seconds % 86400) / 3600;
        long minutes = (seconds % 3600) / 60;
        long secs = seconds % 60;

        StringBuilder sb = new StringBuilder();
        if (days > 0) sb.append(days).append("d ");
        if (hours > 0) sb.append(hours).append("h ");
        if (minutes > 0) sb.append(minutes).append("m ");
        if (secs > 0 || sb.isEmpty()) sb.append(secs).append("s");
        return sb.toString().trim();
    }

    private void logActionFailure(String operation, ActionData actionData, Guild guild, Exception e) {
        if (isPermissionFailure(e)) {
            logger.warn(
                    "Permission denied while trying to {} for user {} in guild {} (actionId={})",
                    operation,
                    actionData.userId(),
                    guild.getId(),
                    actionData.id(),
                    e
            );
            return;
        }

        logger.warn(
                "Failed to {} for user {} in guild {} (actionId={})",
                operation,
                actionData.userId(),
                guild.getId(),
                actionData.id(),
                e
        );
    }

    private boolean isPermissionFailure(Exception e) {
        if (e instanceof InsufficientPermissionException) {
            return true;
        }

        if (e instanceof ErrorResponseException errorResponseException) {
            return errorResponseException.getErrorResponse() == ErrorResponse.MISSING_PERMISSIONS;
        }

        return false;
    }
}
