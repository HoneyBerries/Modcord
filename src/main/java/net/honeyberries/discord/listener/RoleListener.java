package net.honeyberries.discord.listener;

import net.dv8tion.jda.api.events.role.RoleDeleteEvent;
import net.dv8tion.jda.api.hooks.ListenerAdapter;
import net.honeyberries.database.ExcludedUsersRepository;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.discord.RoleID;
import org.jetbrains.annotations.NotNull;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class RoleListener extends ListenerAdapter {

    private final Logger logger = LoggerFactory.getLogger(RoleListener.class);
    private final ExcludedUsersRepository excludedUsersRepository = ExcludedUsersRepository.getInstance();

    @Override
    public void onRoleDelete(@NotNull RoleDeleteEvent event) {
        GuildID guildID = GuildID.fromGuild(event.getGuild());
        RoleID roleID = new RoleID(event.getRole().getIdLong());

        boolean removed = excludedUsersRepository.unmarkExcluded(guildID, roleID);
        if (!removed) {
            logger.warn("Failed to clean up deleted role {} from exclusions in guild {}", roleID.value(), guildID.value());
        }
    }

}
