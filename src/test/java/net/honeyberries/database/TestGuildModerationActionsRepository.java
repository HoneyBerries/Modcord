package net.honeyberries.database;

import net.honeyberries.config.AppConfig;
import net.honeyberries.database.repository.GuildModerationActionsRepository;
import net.honeyberries.datatypes.action.ActionData;
import net.honeyberries.datatypes.action.ActionType;
import net.honeyberries.datatypes.discord.GuildID;
import org.junit.jupiter.api.*;

import java.util.List;
import java.util.Random;

import static org.junit.jupiter.api.Assertions.*;

@DisplayName("Guild Moderation Actions Repository Tests")
@Tag("integration")
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
public class TestGuildModerationActionsRepository {

    private static final Database database = Database.getInstance();
    private static final AppConfig appConfig = AppConfig.getInstance();
    private static final GuildModerationActionsRepository repository = GuildModerationActionsRepository.getInstance();

    // Use your actual test guild ID that has at least 20 non-reversed actions
    private static final long TEST_GUILD_ID = 1488762869880324200L;

    @BeforeAll
    static void setup() {
        database.initialize(appConfig);
    }

    @Test
    @DisplayName("Should retrieve recent actions with limit of 5")
    void testGetRecentActionsLimit5() {
        GuildID guildId = new GuildID(TEST_GUILD_ID);
        List<ActionData> actions = repository.getRecentActiveActions(guildId, 5);

        assertEquals(5, actions.size(), "Should return at most 5 actions");

        // Verify actions are ordered by created_at DESC (no exceptions during retrieval)
        for (ActionData action : actions) {
            assertNotNull(action, "Action should not be null");
            assertNotEquals(ActionType.NULL, action.action(), "NULL actions should be filtered out");
        }

        IO.println("Limit 5 returned: " + actions.size() + " actions");
    }

    @Test
    @DisplayName("Should retrieve recent actions with limit of 2")
    void testGetRecentActionsLimit2() {
        GuildID guildId = new GuildID(TEST_GUILD_ID);
        List<ActionData> actions = repository.getRecentActiveActions(guildId, 2);

        assertEquals(2, actions.size(), "Should return at most 2 actions");

        for (ActionData action : actions) {
            assertNotNull(action, "Action should not be null");
            assertNotEquals(ActionType.NULL, action.action(), "NULL actions should be filtered out");
        }

        IO.println("Limit 2 returned: " + actions.size() + " actions");
    }

    @Test
    @DisplayName("Should retrieve more recent actions with higher limit")
    void testGetRecentActionsWithDifferentLimits() {
        GuildID guildId = new GuildID(TEST_GUILD_ID);

        List<ActionData> limit5 = repository.getRecentActiveActions(guildId, 5);
        List<ActionData> limit10 = repository.getRecentActiveActions(guildId, 10);

        assertTrue(limit5.size() <= limit10.size(), "Limit 5 should return same or fewer than limit 10");
        assertTrue(limit5.size() <= 5, "Limit 5 should return at most 5");
        assertTrue(limit10.size() <= 10, "Limit 10 should return at most 10");

        IO.println("Limit 5: " + limit5.size() + ", Limit 10: " + limit10.size());
    }


    @Test
    @DisplayName("Should retrive more recent actions, with random limit")
    void testGetRecentActionsWithRandomLimit() {
        GuildID guildId = new GuildID(TEST_GUILD_ID);

        Random random = new Random();
        int limit = random.nextInt(1, 20);

        List<ActionData> actions = repository.getRecentActiveActions(guildId, limit);

        assertEquals(actions.size(), limit, "Limit should be at most the number of actions");
    }


    @Test
    @DisplayName("Should retrieve all recent actions with high limit")
    void testGetRecentActionsWithHighLimit() {
        GuildID guildId = new GuildID(TEST_GUILD_ID);

        List<ActionData> allActions = repository.getRecentActiveActions(guildId, 100);

        assertTrue(allActions.size() <= 100, "Should respect the limit of 100");

        // Verify ordering - check that created_at is consistent (no exceptions)
        for (int i = 0; i < allActions.size(); i++) {
            ActionData action = allActions.get(i);
            assertNotNull(action, "Action " + i + " should not be null");
            assertNotEquals(ActionType.NULL, action.action(), "Action should not be NULL type");
        }

        IO.println("High limit returned: " + allActions.size() + " actions");
    }

    @Test
    @DisplayName("Should filter out NULL actions correctly")
    void testNullActionsAreFiltered() {
        GuildID guildId = new GuildID(TEST_GUILD_ID);
        List<ActionData> actions = repository.getRecentActiveActions(guildId, 100);

        for (ActionData action : actions) {
            assertNotEquals(ActionType.NULL, action.action(),
                "NULL type actions should be filtered out from results");
        }

        IO.println("All " + actions.size() + " returned actions have non-NULL action type");
    }

    @Test
    @DisplayName("Should filter out reversed actions correctly")
    void testReversedActionsAreFiltered() {
        GuildID guildId = new GuildID(TEST_GUILD_ID);

        // Get all reversed action IDs from the database
        var reversedIds = Database.getInstance().query(conn -> {
            var ids = new java.util.HashSet<java.util.UUID>();
            String sql = "SELECT action_id FROM guild_moderation_action_reversals";
            try (var stmt = conn.prepareStatement(sql);
                 var rs = stmt.executeQuery()) {
                while (rs.next()) {
                    ids.add((java.util.UUID) rs.getObject("action_id"));
                }
            }
            return ids;
        });

        // Get recent actions
        List<ActionData> recentActions = repository.getRecentActiveActions(guildId, 100);

        // Verify that none of the returned actions have reversals
        for (ActionData action : recentActions) {
            assertFalse(reversedIds.contains(action.id()),
                "Reversed action " + action.id() + " should be filtered out from recent actions");
        }

        IO.println("Query completed successfully. Returned " + recentActions.size() + " non-reversed actions. " +
                   "Verified that " + reversedIds.size() + " reversed actions are correctly excluded.");
    }
}
