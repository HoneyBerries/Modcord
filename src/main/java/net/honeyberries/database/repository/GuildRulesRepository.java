package net.honeyberries.database.repository;

import net.honeyberries.datatypes.content.GuildRules;
import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;

import java.sql.Types;
import java.util.Objects;

/**
 * Persists and retrieves guild moderation rules from the database cache.
 * Associates rules with a guild and optionally with a rules channel for synchronization.
 * Supports upsert operations to refresh rules without key conflicts.
 */
public class GuildRulesRepository extends RepositoryBase {
    /**
     * Singleton instance.
     */
    private static final GuildRulesRepository INSTANCE = new GuildRulesRepository();

    /**
     * Constructs a new repository, retrieving the singleton database instance.
     */
    public GuildRulesRepository() {
        super();
    }

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
        String sql = """
                    INSERT INTO guild_rules (guild_id, rules_channel_id, rules_text)
                    VALUES (?, ?, ?)
                    ON CONFLICT (guild_id) DO UPDATE SET
                        rules_channel_id = EXCLUDED.rules_channel_id,
                        rules_text = EXCLUDED.rules_text
                """;

        return safeTransaction(conn -> {
            try (var ps = conn.prepareStatement(sql)) {
                ps.setLong(1, guildRules.guildId().value());
                ChannelID rulesChannelId = guildRules.rulesChannelId();
                bindNullableLong(ps, 2, rulesChannelId == null ? null : rulesChannelId.value());

                if (guildRules.rulesText() != null) {
                    ps.setString(3, guildRules.rulesText());
                } else {
                    ps.setNull(3, Types.VARCHAR);
                }
                ps.executeUpdate();
            }
        }, "Failed to add/update guild rules in database");
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

        return safeQueryOne(sql, ps -> ps.setLong(1, guildId.value()), rs -> {
            long rulesChannelRaw = rs.getLong("rules_channel_id");
            ChannelID rulesChannelId = rs.wasNull() ? null : new ChannelID(rulesChannelRaw);

            return new GuildRules(
                    new GuildID(rs.getLong("guild_id")),
                    rulesChannelId,
                    rs.getString("rules_text")
            );
        }, "Failed to fetch guild rules from database");
    }

}
