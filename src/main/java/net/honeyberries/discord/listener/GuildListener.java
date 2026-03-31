package net.honeyberries.discord.listener;

import net.dv8tion.jda.api.events.guild.GuildJoinEvent;
import net.dv8tion.jda.api.events.guild.GuildLeaveEvent;
import net.dv8tion.jda.api.hooks.ListenerAdapter;
import net.honeyberries.database.GuildPreferencesRepository;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.preferences.GuildPreferences;
import org.jetbrains.annotations.NotNull;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class GuildListener extends ListenerAdapter {

    private final Logger logger = LoggerFactory.getLogger(GuildListener.class);

    @Override
    public void onGuildJoin(@NotNull GuildJoinEvent event) {
        logger.debug("Joined guild: {}", event.getGuild().getName());

        GuildID guildId = GuildID.fromGuild(event.getGuild());

        // Create default guild preferences for the new guild
        GuildPreferences guildPreferences = new GuildPreferences(guildId);

        // Save preferences to database
        GuildPreferencesRepository.getInstance().addOrUpdateGuildPreferences(guildPreferences);

    }


    @Override
    public void onGuildLeave(@NotNull GuildLeaveEvent event) {
        logger.debug("Left guild: {}", event.getGuild().getName());
        GuildID guildId = GuildID.fromGuild(event.getGuild());

        GuildPreferencesRepository.getInstance().deleteGuildPreferences(guildId);
    }

}
