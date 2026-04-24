package net.honeyberries.discord.listener;

import net.dv8tion.jda.api.events.guild.GuildJoinEvent;
import net.dv8tion.jda.api.events.guild.GuildLeaveEvent;
import net.dv8tion.jda.api.hooks.ListenerAdapter;
import net.honeyberries.database.repository.GuildPreferencesRepository;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.preferences.Onboarding;
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
    }

    /**
     * Cleans up bot state when leaving a guild.
     * Removes stored preferences to avoid orphaned configuration.
     *
     * @param event the guild leave event from Discord
     * @throws NullPointerException if {@code event} is {@code null}
     */
    @Override
    public void onGuildLeave(@NotNull GuildLeaveEvent event) {
        logger.debug("Left guild: {}", event.getGuild().getName());
        GuildID guildId = GuildID.fromGuild(event.getGuild());

        GuildPreferencesRepository.getInstance().deleteGuildPreferences(guildId);
        GlobalOrchestrationService.getInstance().evictGuild(guildId);
    }

}
