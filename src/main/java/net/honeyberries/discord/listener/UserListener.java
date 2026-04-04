package net.honeyberries.discord.listener;

import net.dv8tion.jda.api.events.guild.member.GuildMemberRemoveEvent;
import net.dv8tion.jda.api.hooks.ListenerAdapter;
import net.honeyberries.database.ExcludedUsersRepository;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.discord.UserID;
import org.jetbrains.annotations.NotNull;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Listens to guild member removal events to clean up exclusion list state.
 * Ensures that excluded users are removed from the exclusion list when they leave the guild.
 * Prevents accumulation of stale exclusion entries for departed members.
 */
public class UserListener extends ListenerAdapter {

    /** Logger for user lifecycle events. */
    private final Logger logger = LoggerFactory.getLogger(UserListener.class);
    /** Repository for managing exclusion lists. */
    private final ExcludedUsersRepository excludedUsersRepository = ExcludedUsersRepository.getInstance();

    /**
     * Removes a user from the exclusion list when they leave the guild.
     * Logs a warning if the removal failed, indicating potential data consistency issues.
     *
     * @param event the guild member remove event from Discord
     * @throws NullPointerException if {@code event} is {@code null}
     */
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
