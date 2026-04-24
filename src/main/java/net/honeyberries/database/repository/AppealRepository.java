package net.honeyberries.database.repository;

import net.honeyberries.database.Database;
import net.honeyberries.datatypes.action.ActionData;
import net.honeyberries.datatypes.action.ActionDataBuilder;
import net.honeyberries.datatypes.action.ActionType;
import net.honeyberries.datatypes.action.AppealData;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.discord.UserID;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

/**
 * Persists and retrieves ban/moderation appeal records.
 * <p>
 * Appeals are stored in the {@code moderation_appeals} table with an is_open boolean flag.
 * Each appeal is linked to a specific moderation action via foreign key.
 */
public class AppealRepository {

    private static final Logger logger = LoggerFactory.getLogger(AppealRepository.class);
    private static final AppealRepository INSTANCE = new AppealRepository();
    private final Database database = Database.getInstance();

    private AppealRepository() {}

    /**
     * Returns the singleton instance.
     *
     * @return the singleton {@code AppealRepository}
     */
    @NotNull
    public static AppealRepository getInstance() {
        return INSTANCE;
    }

    /**
     * Creates a new open appeal record for the given guild and user.
     * All appeals must be linked to a specific moderation action.
     *
     * @param guildId  the guild where the action occurred, must not be {@code null}
     * @param userId   Discord snowflake of the appealing user
     * @param actionId the UUID of the moderation action being appealed, must not be {@code null}
     * @param reason   the appeal text, must not be {@code null}
     * @return the UUID assigned to the new appeal, or {@code null} if persistence failed
     * @throws NullPointerException if {@code guildId}, {@code actionId}, or {@code reason} is {@code null}
     */
    @Nullable
    public UUID createAppeal(@NotNull GuildID guildId, @NotNull UserID userId, @NotNull UUID actionId, @NotNull String reason) {
        Objects.requireNonNull(guildId, "guildId must not be null");
        Objects.requireNonNull(actionId, "actionId must not be null");
        Objects.requireNonNull(reason, "reason must not be null");
        UUID id = UUID.randomUUID();
        String sql = """
            INSERT INTO moderation_appeals (appeal_id, guild_id, user_id, action_id, reason, is_open)
            VALUES (?, ?, ?, ?, ?, TRUE)
        """;

        try {
            database.transaction(conn -> {
                try (PreparedStatement ps = conn.prepareStatement(sql)) {
                    ps.setObject(1, id);
                    ps.setLong(2, guildId.value());
                    ps.setLong(3, userId.value());
                    ps.setObject(4, actionId);
                    ps.setString(5, reason);
                    ps.executeUpdate();
                }
            });
            return id;
        } catch (Exception e) {
            logger.error("Failed to create appeal for user {} in guild {}", userId.value(), guildId.value(), e);
            return null;
        }
    }

    /**
     * Marks an appeal as closed in the given guild.
     * Uses guild_id to prevent cross-guild state changes (tenant isolation).
     *
     * @param guildId  the guild where the appeal resides, must not be {@code null}
     * @param appealId the UUID of the appeal to close, must not be {@code null}
     * @param note     moderator's resolution note, must not be {@code null}
     * @return {@code true} if the appeal was found and updated, {@code false} otherwise
     * @throws NullPointerException if {@code guildId}, {@code appealId}, or {@code note} is {@code null}
     */
    public boolean closeAppeal(@NotNull GuildID guildId, @NotNull UUID appealId, @NotNull String note) {
        Objects.requireNonNull(guildId, "guildId must not be null");
        Objects.requireNonNull(appealId, "appealId must not be null");
        Objects.requireNonNull(note, "note must not be null");
        String sql = """
            UPDATE moderation_appeals
            SET is_open = FALSE,
                resolution_note = ?,
                resolved_at = CURRENT_TIMESTAMP
            WHERE appeal_id = ?
              AND guild_id = ?
              AND is_open = TRUE
        """;

        try {
            int updated = database.executeUpdate(conn -> {
                try (PreparedStatement ps = conn.prepareStatement(sql)) {
                    ps.setString(1, note);
                    ps.setObject(2, appealId);
                    ps.setLong(3, guildId.value());
                    return ps.executeUpdate();
                }
            });
            return updated > 0;
        } catch (Exception e) {
            logger.error("Failed to close appeal {} in guild {}", appealId, guildId, e);
            return false;
        }
    }

    /**
     * Retrieves all open appeals for a guild where the underlying action has not been reversed,
     * ordered by submission time (oldest first). Each appeal includes the full action details via JOIN.
     *
     * @param guildId the guild to query, must not be {@code null}
     * @return list of open appeal records with embedded action data, never {@code null}
     * @throws NullPointerException if {@code guildId} is {@code null}
     */
    @NotNull
    public List<AppealData> getOpenAppeals(@NotNull GuildID guildId) {
        Objects.requireNonNull(guildId, "guildId must not be null");
        String sql = """
            SELECT ma.appeal_id, ma.guild_id, ma.user_id, ma.action_id, ma.reason, ma.submitted_at,
                   gma.moderator_id, gma.action, gma.reason AS action_reason,
                   gma.timeout_duration, gma.ban_duration, gma.created_at
            FROM moderation_appeals ma
            JOIN guild_moderation_actions gma ON ma.action_id = gma.action_id
            WHERE ma.guild_id = ?
              AND ma.is_open = TRUE
              AND NOT EXISTS (
                    SELECT 1 FROM guild_moderation_action_reversals r
                    WHERE r.action_id = ma.action_id
                  )
            ORDER BY ma.submitted_at
        """;

        try {
            return database.query(conn -> {
                List<AppealData> results = new ArrayList<>();
                try (PreparedStatement ps = conn.prepareStatement(sql)) {
                    ps.setLong(1, guildId.value());
                    try (ResultSet rs = ps.executeQuery()) {
                        while (rs.next()) {
                            AppealData appeal = mapAppealWithAction(rs);
                            results.add(appeal);
                        }
                    }
                }
                return results;
            });
        } catch (Exception e) {
            logger.error("Failed to fetch open appeals for guild {}", guildId, e);
            return List.of();
        }
    }

    /**
     * Maps a result set row (with joined action columns) into an {@code AppealData} with embedded {@code ActionData}.
     *
     * @param rs result set positioned on an appeal+action row
     * @return reconstructed appeal data with embedded action
     * @throws SQLException if a column cannot be accessed
     */
    @NotNull
    private AppealData mapAppealWithAction(@NotNull ResultSet rs) throws SQLException {
        Objects.requireNonNull(rs, "rs must not be null");

        Instant submittedAt = rs.getTimestamp("submitted_at").toInstant();
        Instant actionCreatedAt = rs.getTimestamp("created_at").toInstant();

        ActionData action = new ActionDataBuilder(
                (UUID) rs.getObject("action_id"),
                actionCreatedAt,
                new GuildID(rs.getLong("guild_id")),
                new UserID(rs.getLong("user_id")),
                new UserID(rs.getLong("moderator_id")),
                ActionType.valueOf(rs.getString("action")),
                rs.getString("action_reason"),
                rs.getLong("timeout_duration"),
                rs.getLong("ban_duration")
        ).build();

        return new AppealData(
                (UUID) rs.getObject("appeal_id"),
                submittedAt,
                new GuildID(rs.getLong("guild_id")),
                new UserID(rs.getLong("user_id")),
                rs.getString("reason"),
                action
        );
    }

    /**
     * Retrieves the UUIDs of all open appeals for a user in a guild.
     * Used to filter out already-appealed actions from the appeal selection menu.
     *
     * @param guildId the guild to query, must not be {@code null}
     * @param userId the user whose appeals to fetch, must not be {@code null}
     * @return list of action_id UUIDs that have open appeals, never {@code null}
     */
    @NotNull
    public List<UUID> getOpenAppealActionIds(@NotNull GuildID guildId, @NotNull UserID userId) {
        Objects.requireNonNull(guildId, "guildId must not be null");
        Objects.requireNonNull(userId, "userId must not be null");
        String sql = """
            SELECT action_id FROM moderation_appeals
            WHERE guild_id = ? AND user_id = ? AND is_open = TRUE AND action_id IS NOT NULL
        """;

        try {
            return database.query(conn -> {
                List<UUID> results = new ArrayList<>();
                try (PreparedStatement ps = conn.prepareStatement(sql)) {
                    ps.setLong(1, guildId.value());
                    ps.setLong(2, userId.value());
                    try (ResultSet rs = ps.executeQuery()) {
                        while (rs.next()) {
                            UUID actionId = (UUID) rs.getObject("action_id");
                            if (actionId != null) {
                                results.add(actionId);
                            }
                        }
                    }
                }
                return results;
            });
        } catch (Exception e) {
            logger.error("Failed to fetch open appeal action IDs for user {} in guild {}", userId, guildId, e);
            return List.of();
        }
    }

    /**
     * Retrieves the UUIDs of all open appeals for a user across all guilds.
     * Used by the appeal system in DMs where the user may be banned from some guilds.
     *
     * @param userId the user whose appeals to fetch, must not be {@code null}
     * @return list of action_id UUIDs that have open appeals, never {@code null}
     */
    @NotNull
    public List<UUID> getAllOpenAppealActionIds(@NotNull UserID userId) {
        Objects.requireNonNull(userId, "userId must not be null");
        String sql = """
            SELECT action_id FROM moderation_appeals
            WHERE user_id = ? AND is_open = TRUE AND action_id IS NOT NULL
        """;

        try {
            return database.query(conn -> {
                List<UUID> results = new ArrayList<>();
                try (PreparedStatement ps = conn.prepareStatement(sql)) {
                    ps.setLong(1, userId.value());
                    try (ResultSet rs = ps.executeQuery()) {
                        while (rs.next()) {
                            UUID actionId = (UUID) rs.getObject("action_id");
                            if (actionId != null) {
                                results.add(actionId);
                            }
                        }
                    }
                }
                return results;
            });
        } catch (Exception e) {
            logger.error("Failed to fetch all open appeal action IDs for user {}", userId, e);
            return List.of();
        }
    }
}
