package net.honeyberries.task;

import net.honeyberries.database.Database;
import net.honeyberries.database.GuildModerationActionsRepository;
import net.honeyberries.datatypes.action.ActionData;
import net.honeyberries.datatypes.action.ActionType;
import net.honeyberries.datatypes.discord.GuildID;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

/**
 * Periodic task that monitors temporary bans and automatically unbans users when their ban duration expires.
 * Runs on a fixed schedule to check all active bans and issue unbans for expired entries.
 * Permanent bans (indicated by sentinel duration value) are never automatically reversed.
 */
public class UnbanWatcherTask implements Runnable {

    /** Logger for task execution and ban expiration events. */
    private static final Logger logger = LoggerFactory.getLogger(UnbanWatcherTask.class);
    /** Repository for querying stored moderation actions. */
    private final GuildModerationActionsRepository actionRepository = GuildModerationActionsRepository.getInstance();
    /** Database connection pool for direct queries. */
    private final Database database = Database.getInstance();

    /**
     * Executes one iteration of the unban watcher task.
     * Fetches all guilds with active bans, then processes each guild to check for expired bans.
     */
    @Override
    public void run() {
        logger.debug("UnbanWatcherTask started");

        try {
            List<GuildID> guildIds = getAllGuildIdsWithBans();

            for (GuildID guildId : guildIds) {
                processBansForGuild(guildId);
            }

            logger.debug("UnbanWatcherTask completed");
        } catch (Exception e) {
            logger.error("Error in UnbanWatcherTask", e);
        }
    }

    /**
     * Retrieves all guilds that have active ban actions recorded.
     * Returns an empty list if a database error occurs.
     *
     * @return a list of guild IDs with ban records, never {@code null}
     */
    private @NotNull List<GuildID> getAllGuildIdsWithBans() {
        String sql = """
            SELECT DISTINCT guild_id
            FROM guild_moderation_actions
            WHERE action = ?
        """;

        try {
            return database.query(conn -> {
                List<GuildID> guildIds = new ArrayList<>();

                try (PreparedStatement ps = conn.prepareStatement(sql)) {
                    ps.setString(1, ActionType.BAN.name());

                    try (ResultSet rs = ps.executeQuery()) {
                        while (rs.next()) {
                            guildIds.add(new GuildID(rs.getLong("guild_id")));
                        }
                    }
                }

                return guildIds;
            });
        } catch (Exception e) {
            logger.error("Failed to fetch guild IDs with bans", e);
            return List.of();
        }
    }

    /**
     * Checks all ban actions in a guild and unbans users whose ban duration has expired.
     * Logs expiration events but does not yet apply the unban to Discord (marked TODO).
     *
     * @param guildId the guild to process
     * @throws NullPointerException if {@code guildId} is {@code null}
     */
    private void processBansForGuild(@NotNull GuildID guildId) {
        java.util.Objects.requireNonNull(guildId, "guildId must not be null");
        try {
            List<ActionData> banActions = actionRepository.getActionsByGuild(guildId)
                    .stream()
                    .filter(a -> a.action() == ActionType.BAN)
                    .toList();

            for (ActionData action : banActions) {
                if (isBanExpired(action)) {
                    logger.info("Ban expired for user {} in guild {}, unbanning...", action.userId(), guildId);

                    // TODO: Implement actual Discord unban logic
                    // 1. Get the Guild object from JDA
                    // 2. Unban the user using guild.unban(userId).queue()
                    // 3. Handle the response/errors appropriately

                    logger.debug("TODO: Unban user {} in guild {}", action.userId(), guildId);
                }
            }
        } catch (Exception e) {
            logger.error("Error processing bans for guild {}", guildId, e);
        }
    }

    /**
     * Determines if a ban action's duration has expired.
     * Permanent bans (sentinel value 2147483647) never expire.
     *
     * @param action the ban action to check
     * @return {@code true} if the ban duration has elapsed; {@code false} if permanent or not yet expired
     * @throws NullPointerException if {@code action} is {@code null}
     */
    private boolean isBanExpired(@NotNull ActionData action) {
        java.util.Objects.requireNonNull(action, "action must not be null");
        if (action.banDuration() == 2147483647L) {
            return false;
        }

        Long createdAtMillis = getActionCreatedTimestamp(action.id());
        if (createdAtMillis == null) {
            logger.warn("Could not find creation timestamp for action {}", action.id());
            return false;
        }

        long expirationTime = createdAtMillis + (action.banDuration() * 1000L);
        return System.currentTimeMillis() >= expirationTime;
    }

    /**
     * Retrieves the creation timestamp of a moderation action.
     *
     * @param actionId the action ID to look up
     * @return the creation timestamp in milliseconds since epoch, or {@code null} if not found or a database error occurred
     * @throws NullPointerException if {@code actionId} is {@code null}
     */
    @Nullable
    private Long getActionCreatedTimestamp(@NotNull UUID actionId) {
        java.util.Objects.requireNonNull(actionId, "actionId must not be null");
        String sql = """
            SELECT created_at
            FROM guild_moderation_actions
            WHERE action_id = ?
        """;

        try {
            return database.query(conn -> {
                try (PreparedStatement ps = conn.prepareStatement(sql)) {
                    ps.setObject(1, actionId);

                    try (ResultSet rs = ps.executeQuery()) {
                        if (rs.next()) {
                            java.sql.Timestamp createdAt = rs.getTimestamp("created_at");
                            if (createdAt != null) {
                                return createdAt.getTime();
                            }
                        }
                    }
                }
                return null;
            });
        } catch (Exception e) {
            logger.error("Failed to fetch creation timestamp for action {}", actionId, e);
            return null;
        }
    }
}