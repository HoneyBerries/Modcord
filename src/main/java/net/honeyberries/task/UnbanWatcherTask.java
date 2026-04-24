package net.honeyberries.task;

import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.UserSnowflake;
import net.dv8tion.jda.api.exceptions.ErrorResponseException;
import net.dv8tion.jda.api.requests.ErrorResponse;
import net.honeyberries.config.AppConfig;
import net.honeyberries.database.Database;
import net.honeyberries.database.repository.GuildModerationActionsRepository;
import net.honeyberries.datatypes.action.ActionData;
import net.honeyberries.datatypes.action.ActionType;
import net.honeyberries.datatypes.discord.GuildID;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.Timestamp;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

/**
 * Periodic task that monitors temporary bans and automatically unbans users when their ban duration expires.
 * Runs on a fixed schedule to check all active bans and issue unbans for expired entries.
 * Permanent bans (indicated by the {@link #PERMANENT_BAN_SENTINEL} duration) are never automatically reversed.
 */
public class UnbanWatcherTask implements Runnable {

    /**
     * Duration sentinel used throughout the system to mark a permanent ban.
     * Matches the historical value written to the database for legacy permanent bans.
     */
    public static final long PERMANENT_BAN_SENTINEL = Integer.MAX_VALUE;

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
     * Each expired ban is attempted via the Discord API; on success, the action row is marked
     * unbanned in the database so subsequent sweeps skip it.
     *
     * @param guildId the guild to process
     * @throws NullPointerException if {@code guildId} is {@code null}
     */
    private void processBansForGuild(@NotNull GuildID guildId) {
        Objects.requireNonNull(guildId, "guildId must not be null");
        try {
            Guild guild = guildId.toGuild();
            if (guild == null) {
                logger.debug("Skipping unban sweep for guild {}: JDA has no reference to the guild", guildId);
                return;
            }

            List<ActionData> banActions = actionRepository.getActionsByGuild(guildId)
                    .stream()
                    .filter(a -> a.action() == ActionType.BAN)
                    .filter(a -> !hasBeenUnbanned(a.id()))
                    .toList();

            for (ActionData action : banActions) {
                if (isBanExpired(action)) {
                    logger.info("Ban expired for user {} in guild {}, unbanning...", action.userId(), guildId);
                    applyUnban(guild, action);
                }
            }
        } catch (Exception e) {
            logger.error("Error processing bans for guild {}", guildId, e);
        }
    }


    /**
     * Issues an unban for the supplied action against Discord and records the reversal in the database.
     * Missing bans (user already unbanned or unknown to Discord) are treated as success so the action
     * is not re-attempted on every sweep.
     *
     * @param guild  guild to unban the user from, must not be {@code null}
     * @param action ban action that has expired, must not be {@code null}
     */
    private void applyUnban(@NotNull Guild guild, @NotNull ActionData action) {
        Objects.requireNonNull(guild, "guild must not be null");
        Objects.requireNonNull(action, "action must not be null");
        try {
            guild.unban(UserSnowflake.fromId(action.userId().value()))
                    .reason("Auto-unban: ban duration expired (action " + action.id() + ")")
                    .timeout(AppConfig.getInstance().getDiscordRequestTimeout(), TimeUnit.SECONDS)
                    .complete();

            recordUnban(action.id(), "expired");
            logger.info("Unbanned user {} in guild {} (action {})",
                    action.userId(), guild.getId(), action.id());

        } catch (ErrorResponseException e) {
            if (e.getErrorResponse() == ErrorResponse.UNKNOWN_BAN) {
                logger.info("User {} in guild {} is no longer banned — marking action {} as reconciled",
                        action.userId(), guild.getId(), action.id());
                recordUnban(action.id(), "already_unbanned");
                return;
            }

            logger.warn("Failed to unban user {} in guild {} (action {}): {}",
                    action.userId(), guild.getId(), action.id(), e.getMeaning());
        } catch (Exception e) {
            logger.warn("Failed to unban user {} in guild {} (action {})",
                    action.userId(), guild.getId(), action.id(), e);
        }
    }


    /**
     * Records that an action has been reversed so future sweeps skip it.
     *
     * @param actionId identifier of the reversed action, must not be {@code null}
     * @param note     short human-readable description of why the reversal occurred
     */
    private void recordUnban(@NotNull UUID actionId, @NotNull String note) {
        Objects.requireNonNull(actionId, "actionId must not be null");
        Objects.requireNonNull(note, "note must not be null");
        String sql = """
            INSERT INTO guild_moderation_action_reversals (action_id, reason, reversed_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT (action_id) DO UPDATE SET
                reason = EXCLUDED.reason,
                reversed_at = EXCLUDED.reversed_at
        """;

        try {
            database.transaction(conn -> {
                try (PreparedStatement ps = conn.prepareStatement(sql)) {
                    ps.setObject(1, actionId);
                    ps.setString(2, note);
                    ps.executeUpdate();
                }
            });
        } catch (Exception e) {
            logger.warn("Failed to record unban reversal for action {}", actionId, e);
        }
    }


    /**
     * Determines whether an action has already been reversed and should be skipped.
     *
     * @param actionId action to check, must not be {@code null}
     * @return {@code true} if a reversal row exists for the action
     */
    private boolean hasBeenUnbanned(@NotNull UUID actionId) {
        Objects.requireNonNull(actionId, "actionId must not be null");
        String sql = """
            SELECT 1
            FROM guild_moderation_action_reversals
            WHERE action_id = ?
            LIMIT 1
        """;
        try {
            return database.query(conn -> {
                try (PreparedStatement ps = conn.prepareStatement(sql)) {
                    ps.setObject(1, actionId);
                    try (ResultSet rs = ps.executeQuery()) {
                        return rs.next();
                    }
                }
            });
        } catch (Exception e) {
            logger.warn("Failed to check reversal status for action {}", actionId, e);
            return false;
        }
    }

    /**
     * Determines if a ban action's duration has expired.
     * Permanent bans (see {@link #PERMANENT_BAN_SENTINEL}) never expire.
     *
     * @param action the ban action to check
     * @return {@code true} if the ban duration has elapsed; {@code false} if permanent or not yet expired
     * @throws NullPointerException if {@code action} is {@code null}
     */
    private boolean isBanExpired(@NotNull ActionData action) {
        Objects.requireNonNull(action, "action must not be null");
        if (action.banDuration() <= 0 || action.banDuration() >= PERMANENT_BAN_SENTINEL) {
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
        Objects.requireNonNull(actionId, "actionId must not be null");
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
                            Timestamp createdAt = rs.getTimestamp("created_at");
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
