package net.honeyberries.database;

import net.honeyberries.database.repository.RetentionRepository;
import net.honeyberries.support.PostgresTestSupport;
import org.junit.jupiter.api.*;

import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;

@DisplayName("Retention Repo Tests")
@Tag("integration")
public class TestRetentionRepo extends PostgresTestSupport {

    private static final Database database = Database.getInstance();
    private final RetentionRepository repository = RetentionRepository.getInstance();

    private static final long GUILD_ID = 424242L;
    private static final long USER_ID = 111L;
    private static final long MOD_ID = 999L;

    @BeforeEach
    void setupGuild() {
        database.transaction(conn -> {
            try (var ps = conn.prepareStatement("INSERT INTO guild_preferences (guild_id) VALUES (?) ON CONFLICT DO NOTHING")) {
                ps.setLong(1, GUILD_ID);
                ps.executeUpdate();
            }
        });
    }

    @AfterEach
    void cleanup() {
        database.transaction(conn -> {
            // Deleting the guild cascades to actions, appeals and reversals.
            try (var ps = conn.prepareStatement("DELETE FROM guild_preferences WHERE guild_id = ?")) {
                ps.setLong(1, GUILD_ID);
                ps.executeUpdate();
            }
        });
    }

    private UUID insertAction(String ageInterval, long banDurationSeconds) {
        UUID id = UUID.randomUUID();
        database.transaction(conn -> {
            try (var ps = conn.prepareStatement("""
                    INSERT INTO guild_moderation_actions
                        (action_id, guild_id, user_id, moderator_id, action, reason, ban_duration, created_at)
                    VALUES (?, ?, ?, ?, 'WARN', 'test', ?, now() - CAST(? AS INTERVAL))
                    """)) {
                ps.setObject(1, id);
                ps.setLong(2, GUILD_ID);
                ps.setLong(3, USER_ID);
                ps.setLong(4, MOD_ID);
                ps.setLong(5, banDurationSeconds);
                ps.setString(6, ageInterval);
                ps.executeUpdate();
            }
        });
        return id;
    }

    private UUID insertAppeal(UUID actionId, boolean open, String resolvedAgo) {
        UUID id = UUID.randomUUID();
        database.transaction(conn -> {
            try (var ps = conn.prepareStatement("""
                    INSERT INTO moderation_appeals
                        (appeal_id, guild_id, user_id, action_id, reason, is_open, resolution_note, resolved_at)
                    VALUES (?, ?, ?, ?, 'please unban me', ?, ?, CASE WHEN ? THEN NULL ELSE now() - CAST(? AS INTERVAL) END)
                    """)) {
                ps.setObject(1, id);
                ps.setLong(2, GUILD_ID);
                ps.setLong(3, USER_ID);
                ps.setObject(4, actionId);
                ps.setBoolean(5, open);
                ps.setString(6, open ? null : "denied");
                ps.setBoolean(7, open);
                ps.setString(8, resolvedAgo == null ? "0 days" : resolvedAgo);
                ps.executeUpdate();
            }
        });
        return id;
    }

    private boolean actionExists(UUID id) {
        return Boolean.TRUE.equals(database.query(conn -> {
            try (var ps = conn.prepareStatement("SELECT 1 FROM guild_moderation_actions WHERE action_id = ?")) {
                ps.setObject(1, id);
                try (var rs = ps.executeQuery()) {
                    return rs.next();
                }
            }
        }));
    }

    private boolean appealExists(UUID id) {
        return Boolean.TRUE.equals(database.query(conn -> {
            try (var ps = conn.prepareStatement("SELECT 1 FROM moderation_appeals WHERE appeal_id = ?")) {
                ps.setObject(1, id);
                try (var rs = ps.executeQuery()) {
                    return rs.next();
                }
            }
        }));
    }

    private String[] appealText(UUID id) {
        return database.query(conn -> {
            try (var ps = conn.prepareStatement("SELECT reason, resolution_note FROM moderation_appeals WHERE appeal_id = ?")) {
                ps.setObject(1, id);
                try (var rs = ps.executeQuery()) {
                    assertTrue(rs.next(), "appeal row should still exist");
                    return new String[]{rs.getString(1), rs.getString(2)};
                }
            }
        });
    }

    @Test
    @DisplayName("Purges only actions older than the retention window")
    void purgesOldActionsOnly() {
        UUID old = insertAction("400 days", 0);
        UUID recent = insertAction("10 days", 0);

        int purged = repository.purgeActionsOlderThan(365);

        assertTrue(purged >= 1);
        assertFalse(actionExists(old));
        assertTrue(actionExists(recent));
    }

    @Test
    @DisplayName("Keeps old actions that still have an open appeal")
    void keepsActionsWithOpenAppeal() {
        UUID old = insertAction("400 days", 0);
        insertAppeal(old, true, null);

        repository.purgeActionsOlderThan(365);

        assertTrue(actionExists(old));
    }

    @Test
    @DisplayName("Purging an action cascades to its resolved appeal")
    void cascadesToResolvedAppeal() {
        UUID old = insertAction("400 days", 0);
        UUID appeal = insertAppeal(old, false, "5 days");

        repository.purgeActionsOlderThan(365);

        assertFalse(actionExists(old));
        assertFalse(appealExists(appeal));
    }

    @Test
    @DisplayName("Keeps old actions whose temporary ban is still running")
    void keepsActionsWithActiveTempBan() {
        // Created 400 days ago, but a 500-day ban (in seconds) has not expired yet.
        UUID activeBan = insertAction("400 days", 500L * 24 * 3600);
        UUID expiredBan = insertAction("400 days", 30L * 24 * 3600);

        repository.purgeActionsOlderThan(365);

        assertTrue(actionExists(activeBan));
        assertFalse(actionExists(expiredBan));
    }

    @Test
    @DisplayName("Blanks free text of appeals resolved before the window, keeping the row")
    void blanksOldResolvedAppealText() {
        UUID action = insertAction("20 days", 0);
        UUID oldResolved = insertAppeal(action, false, "100 days");

        int cleared = repository.clearResolvedAppealTextOlderThan(90);

        assertEquals(1, cleared);
        String[] text = appealText(oldResolved);
        assertEquals("", text[0]);
        assertNull(text[1]);
    }

    @Test
    @DisplayName("Leaves open and recently resolved appeals untouched")
    void keepsOpenAndRecentAppealText() {
        UUID action = insertAction("20 days", 0);
        UUID open = insertAppeal(action, true, null);
        UUID recentResolved = insertAppeal(action, false, "10 days");

        int cleared = repository.clearResolvedAppealTextOlderThan(90);

        assertEquals(0, cleared);
        assertEquals("please unban me", appealText(open)[0]);
        assertEquals("please unban me", appealText(recentResolved)[0]);
    }

    @Test
    @DisplayName("Clearing appeal text is idempotent")
    void clearingIsIdempotent() {
        UUID action = insertAction("20 days", 0);
        insertAppeal(action, false, "100 days");

        assertEquals(1, repository.clearResolvedAppealTextOlderThan(90));
        assertEquals(0, repository.clearResolvedAppealTextOlderThan(90));
    }
}
