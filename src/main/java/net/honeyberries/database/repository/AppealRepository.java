package net.honeyberries.database.repository;

import net.honeyberries.database.Database;
import net.honeyberries.datatypes.content.AppealData;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.discord.UserID;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.sql.PreparedStatement;
import java.sql.ResultSet;
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
     * Optionally links the appeal to a specific moderation action.
     *
     * @param guildId  the guild where the action occurred, must not be {@code null}
     * @param userId   Discord snowflake of the appealing user
     * @param actionId the UUID of the moderation action being appealed, or {@code null} if not known
     * @param reason   the appeal text, must not be {@code null}
     * @return the UUID assigned to the new appeal, or {@code null} if persistence failed
     * @throws NullPointerException if {@code guildId} or {@code reason} is {@code null}
     */
    @Nullable
    public UUID createAppeal(@NotNull GuildID guildId, long userId, @Nullable UUID actionId, @NotNull String reason) {
        Objects.requireNonNull(guildId, "guildId must not be null");
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
                    ps.setLong(3, userId);
                    if (actionId != null) {
                        ps.setObject(4, actionId);
                    } else {
                        ps.setNull(4, java.sql.Types.OTHER);
                    }
                    ps.setString(5, reason);
                    ps.executeUpdate();
                }
            });
            return id;
        } catch (Exception e) {
            logger.error("Failed to create appeal for user {} in guild {}", userId, guildId, e);
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
     * Retrieves all open appeals for a guild, ordered by submission time (oldest first).
     *
     * @param guildId the guild to query, must not be {@code null}
     * @return list of open appeal records, never {@code null}
     * @throws NullPointerException if {@code guildId} is {@code null}
     */
    @NotNull
    public List<AppealData> getOpenAppeals(@NotNull GuildID guildId) {
        Objects.requireNonNull(guildId, "guildId must not be null");
        String sql = """
            SELECT appeal_id, guild_id, user_id, action_id, reason, is_open, submitted_at
            FROM moderation_appeals
            WHERE guild_id = ? AND is_open = TRUE
            ORDER BY submitted_at ASC
        """;

        try {
            return database.query(conn -> {
                List<AppealData> results = new ArrayList<>();
                try (PreparedStatement ps = conn.prepareStatement(sql)) {
                    ps.setLong(1, guildId.value());
                    try (ResultSet rs = ps.executeQuery()) {
                        while (rs.next()) {
                            results.add(new AppealData(
                                    (UUID) rs.getObject("appeal_id"),
                                    new GuildID(rs.getLong("guild_id")),
                                    new UserID(rs.getLong("user_id")),
                                    rs.getString("reason"),
                                    (UUID) rs.getObject("action_id"),
                                    rs.getBoolean("is_open")
                            ));
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
}
