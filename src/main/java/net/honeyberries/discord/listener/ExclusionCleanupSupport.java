package net.honeyberries.discord.listener;

import net.honeyberries.datatypes.discord.GuildID;
import org.jetbrains.annotations.NotNull;
import org.slf4j.Logger;

import java.util.function.BooleanSupplier;

/**
 * Shared cleanup logic for listeners that remove stale exclusion-list entries when an entity
 * (a role or a guild member) is removed from a guild.
 * <p>
 * {@link RoleListener} and {@link UserListener} both react to an entity leaving/being deleted from
 * a guild by unmarking it as excluded, then logging a warning if that cleanup failed. This class
 * centralizes that shared shape so both listeners can delegate to it instead of duplicating it.
 */
final class ExclusionCleanupSupport {

    private ExclusionCleanupSupport() {
        // utility class
    }

    /**
     * Performs an exclusion-list cleanup for a removed entity and logs a warning if it failed.
     *
     * @param logger            logger to emit the warning through; must not be {@code null}
     * @param unmarkAction      the exclusion-repository call to invoke, returning whether the
     *                          entity was successfully unmarked as excluded; must not be {@code null}
     * @param entityDescription short description of the removed entity for the log message,
     *                          e.g. {@code "deleted role"} or {@code "removed user"}; must not be {@code null}
     * @param entityValue       snowflake value of the removed entity, for logging
     * @param guildID           guild the entity belonged to; must not be {@code null}
     */
    static void cleanupExclusionOnRemoval(
            @NotNull Logger logger,
            @NotNull BooleanSupplier unmarkAction,
            @NotNull String entityDescription,
            long entityValue,
            @NotNull GuildID guildID) {
        boolean removed = unmarkAction.getAsBoolean();
        if (!removed) {
            logger.warn("Failed to clean up {} {} from exclusions in guild {}", entityDescription, entityValue, guildID.value());
        }
    }
}
