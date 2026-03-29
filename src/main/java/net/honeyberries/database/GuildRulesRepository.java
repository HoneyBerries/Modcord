package net.honeyberries.database;

import net.honeyberries.datatypes.content.GuildRules;
import net.honeyberries.datatypes.discord.GuildID;
import org.jetbrains.annotations.Nullable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class GuildRulesRepository {
    Logger logger = LoggerFactory.getLogger(GuildRulesRepository.class);
    private final Database database;

    private static final GuildRulesRepository INSTANCE = new GuildRulesRepository();

    public static GuildRulesRepository getInstance() {
        return INSTANCE;
    }

    public GuildRulesRepository() {
        this.database = Database.getInstance();
    }


    public boolean addOrReplaceGuildRulesToDatabase(GuildRules guildRules) {
        try {
            database.transaction(conn -> {
                String sql = """
                    INSERT INTO guild_rules (guild_id, rules_channel_id, rules_text)
                    VALUES (?, ?, ?)
                    ON CONFLICT (guild_id) DO UPDATE SET
                        rules_channel_id = EXCLUDED.rules_channel_id,
                        rules_text = EXCLUDED.rules_text
                """;

                try (var ps = conn.prepareStatement(sql)) {
                    ps.setLong(1, guildRules.guildId().value());
                    ps.setString(3, guildRules.rulesText());
                    ps.executeUpdate();
                }
            });
            return true;
        } catch (Exception e) {
            logger.error("Failed to add/update guild rules in database", e);
            return false;
        }
    }

    @Nullable
    public GuildRules getGuildRules(GuildID guildId) {
        String sql = """
            SELECT guild_id, rules_channel_id, rules_text
            FROM guild_rules
            WHERE guild_id = ?
        """;

        try {
            return database.query(conn -> {
                try (var ps = conn.prepareStatement(sql)) {
                    ps.setLong(1, guildId.value());

                    try (var rs = ps.executeQuery()) {
                        if (rs.next()) {
                            return new GuildRules(
                                new GuildID(rs.getLong("guild_id")),
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