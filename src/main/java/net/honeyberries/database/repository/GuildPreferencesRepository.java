package net.honeyberries.database.repository;

import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.preferences.GuildPreferences;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Objects;

/**
 * Manages the persistence and retrieval of guild-specific moderation preferences.
 * Tracks settings such as AI enablement, auto-moderation actions, and designated channel IDs for notifications.
 * Supports upsert operations to keep preferences in sync with Discord configuration changes.
 */
public class GuildPreferencesRepository extends RepositoryBase {

    /**
     * Singleton instance.
     */
    private static final GuildPreferencesRepository INSTANCE = new GuildPreferencesRepository();

    /**
     * Constructs a new repository, retrieving the singleton database instance.
     */
    public GuildPreferencesRepository() {
        super();
    }

    /**
     * Retrieves the singleton instance of this repository.
     *
     * @return the singleton {@code GuildPreferencesRepository}
     */
    @NotNull
    public static GuildPreferencesRepository getInstance() {
        return INSTANCE;
    }

    /**
     * Persists or updates guild preferences in a single transaction.
     * If preferences for the guild already exist, all fields are replaced; otherwise, new preferences are inserted.
     * Channel IDs are optional and may be {@code null}.
     *
     * @param guildPreferences the preferences to persist or update
     * @return {@code true} if the operation succeeded, {@code false} if a database error occurred
     * @throws NullPointerException if {@code guildPreferences} is {@code null}
     */
    public boolean addOrUpdateGuildPreferences(@NotNull GuildPreferences guildPreferences) {
        Objects.requireNonNull(guildPreferences, "guildPreferences must not be null");
        String upsertSql = """
                    INSERT INTO guild_preferences (
                        guild_id, ai_enabled, rules_channel_id,
                        auto_warn_enabled, auto_delete_enabled, auto_timeout_enabled,
                        auto_kick_enabled, auto_ban_enabled, audit_log_channel_id,
                        remove_on_delete, appeals_enabled
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (guild_id) DO UPDATE SET
                        ai_enabled             = EXCLUDED.ai_enabled,
                        rules_channel_id       = EXCLUDED.rules_channel_id,
                        auto_warn_enabled      = EXCLUDED.auto_warn_enabled,
                        auto_delete_enabled    = EXCLUDED.auto_delete_enabled,
                        auto_timeout_enabled   = EXCLUDED.auto_timeout_enabled,
                        auto_kick_enabled      = EXCLUDED.auto_kick_enabled,
                        auto_ban_enabled       = EXCLUDED.auto_ban_enabled,
                        audit_log_channel_id   = EXCLUDED.audit_log_channel_id,
                        remove_on_delete       = EXCLUDED.remove_on_delete,
                        appeals_enabled        = EXCLUDED.appeals_enabled
                """;

        return safeTransaction(conn -> {
            try (var ps = conn.prepareStatement(upsertSql)) {
                ps.setLong(1, guildPreferences.guildId().value());
                ps.setBoolean(2, guildPreferences.aiEnabled());

                ChannelID rulesChannelID = guildPreferences.rulesChannelID();
                bindNullableLong(ps, 3, rulesChannelID == null ? null : rulesChannelID.value());

                ps.setBoolean(4, guildPreferences.autoWarnEnabled());
                ps.setBoolean(5, guildPreferences.autoDeleteEnabled());
                ps.setBoolean(6, guildPreferences.autoTimeoutEnabled());
                ps.setBoolean(7, guildPreferences.autoKickEnabled());
                ps.setBoolean(8, guildPreferences.autoBanEnabled());

                ChannelID auditLogChannelId = guildPreferences.auditLogChannelId();
                bindNullableLong(ps, 9, auditLogChannelId == null ? null : auditLogChannelId.value());

                ps.setBoolean(10, guildPreferences.removeOnDeleteEnabled());
                ps.setBoolean(11, guildPreferences.appealsEnabled());

                ps.executeUpdate();
            }
        }, "Failed to add/update guild preferences in database");
    }

    /**
     * Retrieves the stored preferences for a specific guild.
     * If no preferences exist, returns {@code null}; this typically means the guild has not yet configured settings.
     *
     * @param guildId the guild ID to look up
     * @return the {@code GuildPreferences} if found, or {@code null} if no settings exist or a database error occurred
     * @throws NullPointerException if {@code guildId} is {@code null}
     */
    @Nullable
    public GuildPreferences getGuildPreferences(@NotNull GuildID guildId) {
        Objects.requireNonNull(guildId, "guildId must not be null");
        String sql = """
                    SELECT guild_id, ai_enabled, rules_channel_id,
                           auto_warn_enabled, auto_delete_enabled, auto_timeout_enabled,
                           auto_kick_enabled, auto_ban_enabled, audit_log_channel_id,
                           remove_on_delete, appeals_enabled
                    FROM guild_preferences
                    WHERE guild_id = ?
                """;

        return safeQueryOne(sql, ps -> ps.setLong(1, guildId.value()), this::mapPreferences,
                "Failed to fetch guild preferences from database");
    }

    /**
     * Removes all stored preferences for a specific guild.
     * Safe to invoke even if no preferences exist for the guild.
     *
     * @param guildId the guild ID to delete preferences for
     * @throws NullPointerException if {@code guildId} is {@code null}
     */
    public void deleteGuildPreferences(@NotNull GuildID guildId) {
        Objects.requireNonNull(guildId, "guildId must not be null");
        String sql = "DELETE FROM guild_preferences WHERE guild_id = ?";

        boolean ok = safeTransaction(conn -> {
            try (var ps = conn.prepareStatement(sql)) {
                ps.setLong(1, guildId.value());
                ps.executeUpdate();
            }
        }, "Failed to delete guild preferences from database");

        if (ok) {
            logger.debug("Deleted guild preferences for guild {}", guildId);
        }
    }

    /**
     * Reconstructs a {@code GuildPreferences} instance from a database result row.
     * Handles nullable channel IDs by checking {@code wasNull()} after retrieving BIGINT values.
     *
     * @param rs the result set positioned at a row from guild_preferences
     * @return the reconstructed {@code GuildPreferences}
     * @throws SQLException if a column cannot be accessed
     */
    @NotNull
    private GuildPreferences mapPreferences(@NotNull ResultSet rs) throws SQLException {
        Objects.requireNonNull(rs, "rs must not be null");
        GuildID guildId = new GuildID(rs.getLong("guild_id"));

        long rulesChannelRaw = rs.getLong("rules_channel_id");
        ChannelID rulesChannelId = rs.wasNull() ? null : new ChannelID(rulesChannelRaw);

        long auditLogRaw = rs.getLong("audit_log_channel_id");
        ChannelID auditLogChannelId = rs.wasNull() ? null : new ChannelID(auditLogRaw);

        return new GuildPreferences(
                guildId,
                rs.getBoolean("ai_enabled"),
                rulesChannelId,
                rs.getBoolean("auto_warn_enabled"),
                rs.getBoolean("auto_delete_enabled"),
                rs.getBoolean("auto_timeout_enabled"),
                rs.getBoolean("auto_kick_enabled"),
                rs.getBoolean("auto_ban_enabled"),
                rs.getBoolean("remove_on_delete"),
                auditLogChannelId,
                rs.getBoolean("appeals_enabled")
        );
    }


}
