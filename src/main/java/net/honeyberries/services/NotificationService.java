package net.honeyberries.services;

import net.dv8tion.jda.api.JDA;
import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.User;
import net.dv8tion.jda.api.entities.channel.concrete.TextChannel;
import net.dv8tion.jda.api.utils.messages.MessageCreateData;
import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.discord.UserID;
import net.honeyberries.datatypes.preferences.GuildPreferences;
import net.honeyberries.discord.JDAManager;
import net.honeyberries.preferences.PreferencesManager;
import org.jetbrains.annotations.NotNull;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Centralised service for all outbound Discord notifications.
 * Owns the two cross-cutting notification patterns shared across the action, rollback, and appeal systems:
 * DM sending and audit channel posting.
 */
public class NotificationService {

    private static final NotificationService INSTANCE = new NotificationService();
    private static final Logger logger = LoggerFactory.getLogger(NotificationService.class);

    private final JDA jda = JDAManager.getInstance().getJDA();

    private NotificationService() {}

    public static NotificationService getInstance() {
        return INSTANCE;
    }

    /**
     * Retrieves the user by ID, opens a DM channel, and sends the message.
     *
     * @param userId  the target user, must not be {@code null}
     * @param message the message to send, must not be {@code null}
     * @return {@code true} if the DM was delivered, {@code false} on any failure
     */
    public boolean sendDm(@NotNull UserID userId, @NotNull MessageCreateData message) {
        try {
            User user = jda.retrieveUserById(userId.value()).complete();
            if (user == null) {
                logger.warn("Cannot send DM: user {} not found", userId.value());
                return false;
            }
            user.openPrivateChannel().complete().sendMessage(message).complete();
            return true;
        } catch (Exception e) {
            logger.warn("Failed to send DM to user {}", userId.value(), e);
            return false;
        }
    }

    /**
     * Posts a message to the guild's configured audit log channel.
     * Silently skips if no audit channel is configured; logs at warn if the channel cannot be found.
     *
     * @param guild   the guild to post in, must not be {@code null}
     * @param message the message to post, must not be {@code null}
     */
    public void postToAuditChannel(@NotNull Guild guild, @NotNull MessageCreateData message) {
        try {
            GuildID guildId = new GuildID(guild.getIdLong());
            GuildPreferences prefs = PreferencesManager.getInstance().getOrDefaultPreferences(guildId);
            ChannelID auditChannelId = prefs.auditLogChannelId();
            if (auditChannelId == null) {
                logger.debug("Audit channel not configured for guild {} — skipping post", guild.getId());
                return;
            }
            TextChannel channel = guild.getTextChannelById(auditChannelId.value());
            if (channel == null) {
                logger.warn("Audit channel {} not found in guild {}", auditChannelId.value(), guild.getId());
                return;
            }
            channel.sendMessage(message).queue(
                    success -> {},
                    error -> logger.warn("Failed to post to audit channel in guild {}", guild.getId(), error)
            );
        } catch (Exception e) {
            logger.warn("Failed to post to audit channel in guild {}", guild.getId(), e);
        }
    }
}
