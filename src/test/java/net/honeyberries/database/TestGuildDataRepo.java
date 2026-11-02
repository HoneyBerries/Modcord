package net.honeyberries.database;

import net.honeyberries.database.repository.GuildDataRepository;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.support.PostgresTestSupport;
import org.junit.jupiter.api.*;

import java.util.List;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;

@DisplayName("Guild Data Purge Tests")
@Tag("integration")
public class TestGuildDataRepo extends PostgresTestSupport {

    private static final Database database = Database.getInstance();
    private static final long GUILD_A = 707001L;
    private static final long GUILD_B = 707002L;
    private static final long SPECIAL_USER = 707999L;

    /** Guild-scoped tables, counted by guild_id (joined through actions for the two child tables). */
    private static final List<String> COUNT_SQL = List.of(
            "SELECT count(*) FROM guild_preferences WHERE guild_id = ?",
            "SELECT count(*) FROM guild_rules WHERE guild_id = ?",
            "SELECT count(*) FROM guild_channel_guidelines WHERE guild_id = ?",
            "SELECT count(*) FROM guild_moderation_exemptions WHERE guild_id = ?",
            "SELECT count(*) FROM guild_moderation_actions WHERE guild_id = ?",
            "SELECT count(*) FROM moderation_appeals WHERE guild_id = ?",
            "SELECT count(*) FROM guild_moderation_action_deletions d JOIN guild_moderation_actions a ON a.action_id = d.action_id WHERE a.guild_id = ?",
            "SELECT count(*) FROM guild_moderation_action_reversals r JOIN guild_moderation_actions a ON a.action_id = r.action_id WHERE a.guild_id = ?"
    );

    @BeforeEach
    void seed() {
        cleanup();
        seedGuild(GUILD_A);
        seedGuild(GUILD_B);
        database.transaction(conn -> {
            try (var ps = conn.prepareStatement(
                    "INSERT INTO special_users (user_id, username) VALUES (?, 'x') ON CONFLICT DO NOTHING")) {
                ps.setLong(1, SPECIAL_USER);
                ps.executeUpdate();
            }
        });
    }

    @AfterEach
    void cleanup() {
        database.transaction(conn -> {
            for (long g : new long[]{GUILD_A, GUILD_B}) {
                try (var ps = conn.prepareStatement("DELETE FROM guild_preferences WHERE guild_id = ?")) {
                    ps.setLong(1, g);
                    ps.executeUpdate();
                }
            }
            try (var ps = conn.prepareStatement("DELETE FROM special_users WHERE user_id = ?")) {
                ps.setLong(1, SPECIAL_USER);
                ps.executeUpdate();
            }
        });
    }

    private void seedGuild(long guildId) {
        UUID actionId = UUID.randomUUID();
        database.transaction(conn -> {
            exec(conn, "INSERT INTO guild_preferences (guild_id) VALUES (?)", guildId);
            exec(conn, "INSERT INTO guild_rules (guild_id, rules_channel_id, rules_text) VALUES (?, 1, 'r')", guildId);
            exec(conn, "INSERT INTO guild_channel_guidelines (guild_id, channel_id, guidelines) VALUES (?, 2, 'g')", guildId);
            exec(conn, "INSERT INTO guild_moderation_exemptions (guild_id, user_id) VALUES (?, 3)", guildId);
            try (var ps = conn.prepareStatement("""
                    INSERT INTO guild_moderation_actions (action_id, guild_id, user_id, moderator_id, action, reason)
                    VALUES (?, ?, 4, 5, 'BAN', 'test')
                    """)) {
                ps.setObject(1, actionId);
                ps.setLong(2, guildId);
                ps.executeUpdate();
            }
            try (var ps = conn.prepareStatement(
                    "INSERT INTO guild_moderation_action_deletions (action_id, channel_id, message_id) VALUES (?, 2, 6)")) {
                ps.setObject(1, actionId);
                ps.executeUpdate();
            }
            try (var ps = conn.prepareStatement(
                    "INSERT INTO guild_moderation_action_reversals (action_id, reason) VALUES (?, 'r')")) {
                ps.setObject(1, actionId);
                ps.executeUpdate();
            }
            try (var ps = conn.prepareStatement("""
                    INSERT INTO moderation_appeals (guild_id, user_id, action_id, reason) VALUES (?, 4, ?, 'please')
                    """)) {
                ps.setLong(1, guildId);
                ps.setObject(2, actionId);
                ps.executeUpdate();
            }
        });
    }

    private static void exec(java.sql.Connection conn, String sql, long guildId) throws java.sql.SQLException {
        try (var ps = conn.prepareStatement(sql)) {
            ps.setLong(1, guildId);
            ps.executeUpdate();
        }
    }

    private int total(long guildId) {
        int sum = 0;
        for (String sql : COUNT_SQL) {
            Integer n = database.query(conn -> {
                try (var ps = conn.prepareStatement(sql)) {
                    ps.setLong(1, guildId);
                    try (var rs = ps.executeQuery()) {
                        rs.next();
                        return rs.getInt(1);
                    }
                }
            });
            sum += n;
        }
        return sum;
    }

    @Test
    @DisplayName("purge removes every row of one guild and leaves the other untouched")
    void purgeIsolatedToGuild() {
        assertEquals(COUNT_SQL.size(), total(GUILD_A));
        assertEquals(COUNT_SQL.size(), total(GUILD_B));

        assertTrue(GuildDataRepository.getInstance().purgeGuildData(new GuildID(GUILD_A)));

        assertEquals(0, total(GUILD_A));
        assertEquals(COUNT_SQL.size(), total(GUILD_B));

        Integer special = database.query(conn -> {
            try (var ps = conn.prepareStatement("SELECT count(*) FROM special_users WHERE user_id = ?")) {
                ps.setLong(1, SPECIAL_USER);
                try (var rs = ps.executeQuery()) {
                    rs.next();
                    return rs.getInt(1);
                }
            }
        });
        assertEquals(1, special, "global special_users must be untouched");
    }

    @Test
    @DisplayName("purging a guild with no data succeeds")
    void purgeUnknownGuildIsNoop() {
        assertTrue(GuildDataRepository.getInstance().purgeGuildData(new GuildID(GUILD_A + 5000)));
        assertEquals(COUNT_SQL.size(), total(GUILD_B));
    }
}
