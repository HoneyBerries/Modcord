package net.honeyberries.database;

import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.preferences.GuildPreferences;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public class GuildPreferencesRepository {

    Logger logger = LoggerFactory.getLogger(GuildPreferencesRepository.class);
    private final Database database;

    private static final GuildPreferencesRepository INSTANCE = new GuildPreferencesRepository();

    @NotNull
    public static GuildPreferencesRepository getInstance() {
        return INSTANCE;
    }

    public GuildPreferencesRepository() {
        this.database = Database.getInstance();
    }


    /**
     * Inserts or updates guild preferences.
     * @param guildPreferences The preferences to save
     * @return true if saved successfully, false otherwise
     */
    public boolean addOrUpdateGuildPreferences(@NotNull GuildPreferences guildPreferences) {
        try {
            database.transaction(conn -> {
                String upsertSql = """
                    INSERT INTO guild_preferences (
                        guild_id, ai_enabled, rules_channel_id,
                        auto_warn_enabled, auto_delete_enabled, auto_timeout_enabled,
                        auto_kick_enabled, auto_ban_enabled, audit_log_channel_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (guild_id) DO UPDATE SET
                        ai_enabled             = EXCLUDED.ai_enabled,
                        rules_channel_id       = EXCLUDED.rules_channel_id,
                        auto_warn_enabled      = EXCLUDED.auto_warn_enabled,
                        auto_delete_enabled    = EXCLUDED.auto_delete_enabled,
                        auto_timeout_enabled   = EXCLUDED.auto_timeout_enabled,
                        auto_kick_enabled      = EXCLUDED.auto_kick_enabled,
                        auto_ban_enabled       = EXCLUDED.auto_ban_enabled,
                        audit_log_channel_id   = EXCLUDED.audit_log_channel_id
                """;

                try (PreparedStatement ps = conn.prepareStatement(upsertSql)) {
                    ps.setLong(1, guildPreferences.guildId().value());
                    ps.setBoolean(2, guildPreferences.aiEnabled());
                    ps.setLong(3, guildPreferences.rulesChannelID().value());
                    ps.setBoolean(4, guildPreferences.autoWarnEnabled());
                    ps.setBoolean(5, guildPreferences.autoDeleteEnabled());
                    ps.setBoolean(6, guildPreferences.autoTimeoutEnabled());
                    ps.setBoolean(7, guildPreferences.autoKickEnabled());
                    ps.setBoolean(8, guildPreferences.autoBanEnabled());

                    ChannelID auditLogChannelId = guildPreferences.auditLogChannelId();
                    if (auditLogChannelId != null) {
                        ps.setLong(9, auditLogChannelId.value());
                    } else {
                        ps.setNull(9, java.sql.Types.BIGINT);
                    }

                    ps.executeUpdate();
                }
            });

            return true;
        } catch (Exception e) {
            logger.error("Failed to add/update guild preferences in database", e);
            return false;
        }
    }


    @Nullable
    public GuildPreferences getGuildPreferences(@NotNull GuildID guildId) {
        String sql = """
            SELECT guild_id, ai_enabled, rules_channel_id,
                   auto_warn_enabled, auto_delete_enabled, auto_timeout_enabled,
                   auto_kick_enabled, auto_ban_enabled, audit_log_channel_id
            FROM guild_preferences
            WHERE guild_id = ?
        """;

        try {
            return database.query(conn -> {
                try (PreparedStatement ps = conn.prepareStatement(sql)) {
                    ps.setLong(1, guildId.value());

                    try (ResultSet rs = ps.executeQuery()) {
                        if (rs.next()) {
                            return mapPreferences(rs);
                        }
                        return null;
                    }
                }
            });
        } catch (Exception e) {
            logger.error("Failed to fetch guild preferences from database", e);
            return null;
        }
    }


    public void deleteGuildPreferences(GuildID guildId) {
        String sql = "DELETE FROM guild_preferences WHERE guild_id = ?";

        try {
            database.transaction(conn -> {
                try (PreparedStatement ps = conn.prepareStatement(sql)) {
                    ps.setLong(1, guildId.value());
                    ps.executeUpdate();
                }
            });
            logger.debug("Deleted guild preferences for guild {}", guildId);
        } catch (Exception e) {
            logger.error("Failed to delete guild preferences from database", e);
        }
    }


    @NotNull
    private GuildPreferences mapPreferences(ResultSet rs) throws SQLException {
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
            auditLogChannelId
        );
    }



}
