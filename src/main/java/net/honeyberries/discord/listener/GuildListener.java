package net.honeyberries.discord.listener;

import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.channel.concrete.TextChannel;
import net.dv8tion.jda.api.events.guild.GuildJoinEvent;
import net.dv8tion.jda.api.events.guild.GuildLeaveEvent;
import net.dv8tion.jda.api.hooks.ListenerAdapter;
import net.honeyberries.database.repository.GuildDataRepository;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.preferences.GuildPreferences;
import net.honeyberries.preferences.Onboarding;
import net.honeyberries.preferences.PreferencesManager;
import net.honeyberries.ui.WelcomeEmbedUI;
import net.honeyberries.services.GlobalOrchestrationService;
import org.jetbrains.annotations.NotNull;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Listens to Discord guild membership events (join, leave) to manage bot lifecycle.
 * Handles onboarding when the bot joins a guild and cleanup when it leaves.
 * Ensures guild configuration is initialized and disposed appropriately.
 */
public class GuildListener extends ListenerAdapter {

    /** Logger for guild lifecycle events. */
    private final Logger logger = LoggerFactory.getLogger(GuildListener.class);

    /**
     * Executes initialization tasks when the bot joins a new guild.
     * Triggers onboarding to set up default preferences and prepare channels.
     *
     * @param event the guild join event from Discord
     * @throws NullPointerException if {@code event} is {@code null}
     */
    @Override
    public void onGuildJoin(@NotNull GuildJoinEvent event) {
        logger.debug("Joined guild: {}", event.getGuild().getName());

        boolean success = Onboarding.getInstance().setupGuild(event.getGuild());
        if (!success) {
            logger.error("Failed to onboard guild {}", event.getGuild().getName());
        }

        try {
            postWelcome(event.getGuild());
        } catch (RuntimeException e) {
            logger.warn("Failed to post welcome message in guild {}", event.getGuild().getName(), e);
        }
    }

    /**
     * Posts the welcome message to the guild's audit channel, if one is set and the bot can talk in it.
     */
    private void postWelcome(@NotNull Guild guild) {
        GuildPreferences prefs = PreferencesManager.getInstance()
                .getOrDefaultPreferences(GuildID.fromGuild(guild));
        if (prefs.auditLogChannelId() == null) {
            logger.info("No audit channel set for the welcome message in guild {}", guild.getName());
            return;
        }

        // Cache lookup is safe here: onboarding just resolved or created this channel from the same guild cache.
        TextChannel audit = guild.getTextChannelById(prefs.auditLogChannelId().value());
        if (audit == null || !audit.canTalk()) {
            logger.info("Audit channel unusable for the welcome message in guild {}", guild.getName());
            return;
        }

        audit.sendMessageEmbeds(WelcomeEmbedUI.build(prefs)).queue(
                null, e -> logger.warn("Could not post welcome in guild {}", guild.getName(), e));
    }

    /**
     * Cleans up bot state when leaving a guild.
     * Evicts in-memory state, then deletes all of the guild's stored data (rules, guidelines, exemptions,
     * moderation actions and dependents, appeals, preferences).
     *
     * @param event the guild leave event from Discord
     * @throws NullPointerException if {@code event} is {@code null}
     */
    @Override
    public void onGuildLeave(@NotNull GuildLeaveEvent event) {
        logger.debug("Left guild: {}", event.getGuild().getName());
        GuildID guildId = GuildID.fromGuild(event.getGuild());

        // Each step is isolated so one failure cannot skip the other or propagate out of the listener.
        try {
            GlobalOrchestrationService.getInstance().evictGuild(guildId);
        } catch (RuntimeException e) {
            logger.error("Failed to evict in-memory state for guild {}", guildId.value(), e);
        }

        try {
            if (!GuildDataRepository.getInstance().purgeGuildData(guildId)) {
                logger.error("Stored data for guild {} could not be purged after leaving it", guildId.value());
            }
        } catch (RuntimeException e) {
            logger.error("Failed to purge stored data for guild {}", guildId.value(), e);
        }
    }

}
