package net.honeyberries.database;

import net.honeyberries.datatypes.discord.GuildID;
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
 * Appeals are stored in the {@code moderation_appeals} table with an open/closed status.
 * Each appeal tracks who submitted it, why, and optionally how it was resolved.
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
     *
     * @param guildId the guild where the action occurred, must not be {@code null}
     * @param userId  Discord snowflake of the appealing user
     * @param reason  the appeal text, must not be {@code null}
     * @return the UUID assigned to the new appeal, or {@code null} if persistence failed
     * @throws NullPointerException if {@code guildId} or {@code reason} is {@code null}
     */
    @Nullable
    public UUID createAppeal(@NotNull GuildID guildId, long userId, @NotNull String reason) {
        Objects.requireNonNull(guildId, "guildId must not be null");
        Objects.requireNonNull(reason, "reason must not be null");
        UUID id = UUID.randomUUID();
        String sql = """
            INSERT INTO moderation_appeals (appeal_id, guild_id, user_id, reason, status)
            VALUES (?, ?, ?, ?, 'open')
        """;

        try {
            database.transaction(conn -> {
                try (PreparedStatement ps = conn.prepareStatement(sql)) {
                    ps.setObject(1, id);
                    ps.setLong(2, guildId.value());
                    ps.setLong(3, userId);
                    ps.setString(4, reason);
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
     * Marks an appeal as closed with an optional resolution note.
     *
     * @param appealId the UUID of the appeal to close, must not be {@code null}
     * @param note     moderator's resolution note, must not be {@code null}
     * @return {@code true} if the appeal was found and updated, {@code false} otherwise
     * @throws NullPointerException if {@code appealId} or {@code note} is {@code null}
     */
    public boolean closeAppeal(@NotNull UUID appealId, @NotNull String note) {
        Objects.requireNonNull(appealId, "appealId must not be null");
        Objects.requireNonNull(note, "note must not be null");
        String sql = """
            UPDATE moderation_appeals
            SET status = 'closed',
                resolution_note = ?,
                resolved_at = CURRENT_TIMESTAMP
            WHERE appeal_id = ?
              AND status = 'open'
        """;

        try {
            int updated = database.executeUpdate(conn -> {
                try (PreparedStatement ps = conn.prepareStatement(sql)) {
                    ps.setString(1, note);
                    ps.setObject(2, appealId);
                    return ps.executeUpdate();
                }
            });
            return updated > 0;
        } catch (Exception e) {
            logger.error("Failed to close appeal {}", appealId, e);
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
    public List<AppealRecord> getOpenAppeals(@NotNull GuildID guildId) {
        Objects.requireNonNull(guildId, "guildId must not be null");
        String sql = """
            SELECT appeal_id, user_id, reason, submitted_at
            FROM moderation_appeals
            WHERE guild_id = ? AND status = 'open'
            ORDER BY submitted_at ASC
        """;

        try {
            return database.query(conn -> {
                List<AppealRecord> results = new ArrayList<>();
                try (PreparedStatement ps = conn.prepareStatement(sql)) {
                    ps.setLong(1, guildId.value());
                    try (ResultSet rs = ps.executeQuery()) {
                        while (rs.next()) {
                            results.add(new AppealRecord(
                                    (UUID) rs.getObject("appeal_id"),
                                    rs.getLong("user_id"),
                                    rs.getString("reason")
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

    /**
     * Lightweight projection of an appeal row for display in slash command responses.
     *
     * @param id     the appeal UUID
     * @param userId Discord snowflake of the appellant
     * @param reason the appeal text
     */
    public record AppealRecord(@NotNull UUID id, long userId, @NotNull String reason) {}
}
