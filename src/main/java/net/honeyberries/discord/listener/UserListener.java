package net.honeyberries.discord.listener;

import net.dv8tion.jda.api.events.guild.member.GuildMemberRemoveEvent;
import net.dv8tion.jda.api.hooks.ListenerAdapter;
import net.honeyberries.database.ExcludedUsersRepository;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.discord.UserID;
import org.jetbrains.annotations.NotNull;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class UserListener extends ListenerAdapter {

    private final Logger logger = LoggerFactory.getLogger(UserListener.class);
    private final ExcludedUsersRepository excludedUsersRepository = ExcludedUsersRepository.getInstance();

    @Override
    public void onGuildMemberRemove(@NotNull GuildMemberRemoveEvent event) {
        GuildID guildID = GuildID.fromGuild(event.getGuild());
        UserID userID = new UserID(event.getUser().getIdLong());

        boolean removed = excludedUsersRepository.unmarkExcluded(guildID, userID);
        if (!removed) {
            logger.warn("Failed to clean up removed user {} from exclusions in guild {}", userID.value(), guildID.value());
        }
    }

}
