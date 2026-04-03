package net.honeyberries.database;

import net.honeyberries.datatypes.content.GuildRules;
import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.util.Objects;

/**
 * Persists and retrieves guild moderation rules from the database cache.
 * Associates rules with a guild and optionally with a rules channel for synchronization.
 * Supports upsert operations to refresh rules without key conflicts.
 */
public class GuildRulesRepository {
    /** Logger for recording database operations. */
    private final Logger logger = LoggerFactory.getLogger(GuildRulesRepository.class);
    /** Database connection pool. */
    private final Database database;
    /** Singleton instance. */
    private static final GuildRulesRepository INSTANCE = new GuildRulesRepository();

    /**
     * Retrieves the singleton instance of this repository.
     *
     * @return the singleton {@code GuildRulesRepository}
     */
    @NotNull
    public static GuildRulesRepository getInstance() {
        return INSTANCE;
    }

    /**
     * Constructs a new repository, retrieving the singleton database instance.
     */
    public GuildRulesRepository() {
        this.database = Database.getInstance();
    }

    /**
     * Persists or updates guild rules in the database cache.
     * If rules for the guild already exist, they are replaced; otherwise, new rules are inserted.
     * The rules channel ID is optional and may be {@code null}.
     *
     * @param guildRules the rules to persist or update
     * @return {@code true} if the operation succeeded, {@code false} if a database error occurred
     * @throws NullPointerException if {@code guildRules} is {@code null}
     */
    public boolean addOrReplaceGuildRulesToDatabase(@NotNull GuildRules guildRules) {
        Objects.requireNonNull(guildRules, "guildRules must not be null");
        try {
            database.transaction(conn -> {
                String sql = """
                    INSERT INTO guild_rules (guild_id, rules_channel_id, rules_text)
                    VALUES (?, ?, ?)
                    ON CONFLICT (guild_id) DO UPDATE SET
                        rules_channel_id = EXCLUDED.rules_channel_id,
                        rules_text = EXCLUDED.rules_text
                """;

                try (PreparedStatement ps = conn.prepareStatement(sql)) {
                    ps.setLong(1, guildRules.guildId().value());
                    if (guildRules.rulesChannelId() != null) {
                        ps.setLong(2, guildRules.rulesChannelId().value());
                    } else {
                        ps.setNull(2, java.sql.Types.BIGINT);
                    }

                    if (guildRules.rulesText() != null) {
                        ps.setString(3, guildRules.rulesText());
                    } else {
                        ps.setNull(3, java.sql.Types.VARCHAR);
                    }
                    ps.executeUpdate();
                }
            });
            return true;
        } catch (Exception e) {
            logger.error("Failed to add/update guild rules in database", e);
            return false;
        }
    }

    /**
     * Retrieves cached guild rules for a specific guild.
     * The method name reflects the intent: rules are read from the database cache, which may be stale until synchronization tasks refresh them.
     *
     * @param guildId the guild ID to look up
     * @return the {@code GuildRules} if found, or {@code null} if no rules exist or a database error occurred
     * @throws NullPointerException if {@code guildId} is {@code null}
     */
    @Nullable
    public GuildRules getGuildRulesFromCache(@NotNull GuildID guildId) {
        Objects.requireNonNull(guildId, "guildId must not be null");
        String sql = """
            SELECT guild_id, rules_channel_id, rules_text
            FROM guild_rules
            WHERE guild_id = ?
        """;

        try {
            return database.query(conn -> {
                try (PreparedStatement ps = conn.prepareStatement(sql)) {
                    ps.setLong(1, guildId.value());

                    try (ResultSet rs = ps.executeQuery()) {
                        if (rs.next()) {
                            long rulesChannelRaw = rs.getLong("rules_channel_id");
                            ChannelID rulesChannelId = rs.wasNull() ? null : new ChannelID(rulesChannelRaw);

                            return new GuildRules(
                                new GuildID(rs.getLong("guild_id")),
                                rulesChannelId,
                                rs.getString("rules_text")
                            );
                        }
                        return null;
                    }
                }
            });
        } catch (Exception e) {
            logger.error("Failed to fetch guild rules from database", e);
            return null;
        }
    }

}