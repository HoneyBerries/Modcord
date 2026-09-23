package net.honeyberries.util;

import net.dv8tion.jda.api.entities.Guild;
import net.honeyberries.database.repository.GuildPreferencesRepository;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.preferences.GuildPreferences;
import net.honeyberries.preferences.Onboarding;
import org.jetbrains.annotations.NotNull;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Shared helper for scheduled tasks that need to guarantee a guild is present in the
 * {@code guild_preferences} table before inserting rows that reference it via a foreign key
 * (e.g. guild rules, channel guidelines).
 */
public final class GuildEnsurer {

    private static final Logger logger = LoggerFactory.getLogger(GuildEnsurer.class);

    private GuildEnsurer() {
        // Utility class; not instantiable.
    }

    /**
     * Ensures the guild exists in the database, onboarding it with default preferences if necessary.
     *
     * @param guildId the identifier of the guild to check; must not be null
     * @param guild   the guild entity to onboard if it does not already exist; must not be null
     * @return {@code true} if the guild already existed or was successfully onboarded, {@code false} otherwise
     */
    public static boolean ensureGuildExists(@NotNull GuildID guildId, @NotNull Guild guild) {
        GuildPreferences existing = GuildPreferencesRepository.getInstance().getGuildPreferences(guildId);
        if (existing != null) {
            return true;
        }

        logger.debug("Guild {} not found in database, onboarding with default preferences", guildId.value());
        boolean success = Onboarding.getInstance().setupGuild(guild);
        if (!success) {
            logger.error("Failed to onboard guild {}", guildId.value());
        }
        return success;
    }
}
