package net.honeyberries.discord.listener;

import net.dv8tion.jda.api.events.role.RoleDeleteEvent;
import net.dv8tion.jda.api.hooks.ListenerAdapter;
import net.honeyberries.database.ExcludedEntitiesRepository;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.discord.RoleID;
import org.jetbrains.annotations.NotNull;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Listens to role deletion events to clean up exclusion list state.
 * Ensures that roles removed from the guild are also removed from the exclusion list.
 * Prevents accumulation of stale role exclusions when roles are deleted.
 */
public class RoleListener extends ListenerAdapter {

    /** Logger for role lifecycle events. */
    private final Logger logger = LoggerFactory.getLogger(RoleListener.class);
    /** Repository for managing exclusion lists. */
    private final ExcludedEntitiesRepository excludedEntitiesRepository = ExcludedEntitiesRepository.getInstance();

    /**
     * Removes a role from the exclusion list when it is deleted from the guild.
     * Logs a warning if the removal failed, indicating potential data consistency issues.
     *
     * @param event the role delete event from Discord
     * @throws NullPointerException if {@code event} is {@code null}
     */
    @Override
    public void onRoleDelete(@NotNull RoleDeleteEvent event) {
        GuildID guildID = GuildID.fromGuild(event.getGuild());
        RoleID roleID = new RoleID(event.getRole().getIdLong());

        boolean removed = excludedEntitiesRepository.unmarkExcluded(guildID, roleID);
        if (!removed) {
            logger.warn("Failed to clean up deleted role {} from exclusions in guild {}", roleID.value(), guildID.value());
        }
    }

}
