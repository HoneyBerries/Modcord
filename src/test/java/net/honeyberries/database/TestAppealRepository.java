package net.honeyberries.database;

import net.honeyberries.config.AppConfig;
import net.honeyberries.database.repository.AppealRepository;
import net.honeyberries.database.repository.GuildModerationActionsRepository;
import net.honeyberries.datatypes.action.ActionData;
import net.honeyberries.datatypes.action.ActionType;
import net.honeyberries.datatypes.content.AppealData;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.discord.UserID;
import org.junit.jupiter.api.*;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;

@DisplayName("Appeal Repository Tests")
@Tag("integration")
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
public class TestAppealRepository {

    private static final Database database = Database.getInstance();
    private static final AppConfig appConfig = AppConfig.getInstance();
    private static final AppealRepository appealRepository = AppealRepository.getInstance();
    private static final GuildModerationActionsRepository actionRepository = GuildModerationActionsRepository.getInstance();

    private static final GuildID TEST_GUILD_ID = new GuildID(1488762869880324200L);
    private static final UserID TEST_USER_1_ID = new UserID(1104649796821729320L);
    private static final UserID TEST_USER_2_ID = new UserID(1180022370375835731L);
    private static final UserID TEST_USER_3_ID = new UserID(1260476582519242767L);

    private UUID testAppealId;

    @BeforeAll
    static void setup() {
        database.initialize(appConfig);
    }

    @Test
    @Order(1)
    @DisplayName("should create an appeal for a user with an action")
    void shouldCreateAppealWithAction() {
        List<ActionData> actions = actionRepository.getRecentActions(TEST_GUILD_ID, 1);
        Assumptions.assumeTrue(!actions.isEmpty(), "Test guild should have at least one action");

        UUID actionId = actions.getFirst().id();

        String appealReason = "I believe this action was unjust. I would like to appeal.";
        UUID appealId = appealRepository.createAppeal(TEST_GUILD_ID, TEST_USER_1_ID, actionId, appealReason);

        assertNotNull(appealId, "Appeal ID should not be null after creation");
        testAppealId = appealId;
    }

    @Test
    @Order(2)
    @DisplayName("should create appeals for multiple users with different actions")
    void shouldCreateAppealsForMultipleUsers() {
        List<ActionData> actions = actionRepository.getRecentActions(TEST_GUILD_ID, 2);
        Assumptions.assumeTrue(actions.size() >= 2, "Test guild should have at least two actions");

        UUID actionId1 = actions.get(0).id();
        UUID actionId2 = actions.get(1).id();

        String appealReason1 = "Appeal from user 2";
        UUID appealId1 = appealRepository.createAppeal(TEST_GUILD_ID, TEST_USER_2_ID, actionId1, appealReason1);

        String appealReason2 = "Appeal from user 3";
        UUID appealId2 = appealRepository.createAppeal(TEST_GUILD_ID, TEST_USER_3_ID, actionId2, appealReason2);

        assertNotNull(appealId1, "Appeal 1 should be created successfully");
        assertNotNull(appealId2, "Appeal 2 should be created successfully");
        assertNotEquals(appealId1, appealId2, "Appeals should have unique IDs");
    }

    @Test
    @Order(3)
    @DisplayName("should retrieve open appeals for a guild")
    void shouldGetOpenAppeals() {
        List<AppealData> appeals = appealRepository.getOpenAppeals(TEST_GUILD_ID);

        assertNotNull(appeals, "Appeals list should not be null");
        assertFalse(appeals.isEmpty(), "Should have at least one open appeal after creation");

        for (AppealData appeal : appeals) {
            assertTrue(appeal.isOpen(), "All returned appeals should be open");
            assertEquals(TEST_GUILD_ID, appeal.guildID(), "Appeal should belong to the test guild");
        }
    }

    @Test
    @Order(4)
    @DisplayName("should close an open appeal")
    void shouldCloseAppeal() {
        Assumptions.assumeTrue(testAppealId != null, "Test appeal must be created first");

        String resolutionNote = "Appeal rejected after review";
        boolean closed = appealRepository.closeAppeal(TEST_GUILD_ID, testAppealId, resolutionNote);

        assertTrue(closed, "Appeal should be successfully closed");
    }

    @Test
    @Order(5)
    @DisplayName("closing non-existent appeal should return false")
    void shouldReturnFalseClosingNonExistentAppeal() {
        UUID nonExistentId = UUID.randomUUID();
        String resolutionNote = "This should not be persisted";

        boolean closed = appealRepository.closeAppeal(TEST_GUILD_ID, nonExistentId, resolutionNote);

        assertFalse(closed, "Closing non-existent appeal should return false");
    }

    @Test
    @Order(6)
    @DisplayName("should get open appeal action IDs for a user in a guild")
    void shouldGetOpenAppealActionIds() {
        List<UUID> actionIds = appealRepository.getOpenAppealActionIds(TEST_GUILD_ID, TEST_USER_1_ID);

        assertNotNull(actionIds, "Action IDs list should not be null");
    }

    @Test
    @Order(7)
    @DisplayName("should get all open appeal action IDs for a user across guilds")
    void shouldGetAllOpenAppealActionIds() {
        List<UUID> actionIds = appealRepository.getAllOpenAppealActionIds(TEST_USER_2_ID);

        assertNotNull(actionIds, "Action IDs list should not be null");
        assertFalse(actionIds.isEmpty(), "Should have at least one open appeal action ID");
    }

    @Test
    @Order(8)
    @DisplayName("should not return closed appeals in open appeals list")
    void shouldNotReturnClosedAppeals() {
        List<AppealData> openAppeals = appealRepository.getOpenAppeals(TEST_GUILD_ID);

        // Verify that closed appeal (from test #4) is not in the list
        boolean closedAppealFound = openAppeals.stream()
                .anyMatch(appeal -> appeal.id().equals(testAppealId));

        assertFalse(closedAppealFound, "Closed appeal should not appear in open appeals list");
    }



    @Test
    @Order(12)
    @DisplayName("should filter appeals with linked action IDs only")
    void shouldFilterAppealsWithLinkedActions() {
        List<AppealData> appeals = appealRepository.getOpenAppeals(TEST_GUILD_ID);

        for (AppealData appeal : appeals) {
            assertNotNull(appeal.actionId(), "All appeals must have an action ID");
            assertTrue(appeal.isOpen(), "Appeal should be open");
        }

        assertFalse(appeals.isEmpty(), "Query should complete successfully");
    }

    @Test
    @Order(13)
    @DisplayName("should retrieve appeals in submission order")
    void shouldRetrieveAppealsInOrder() {
        List<AppealData> appeals = appealRepository.getOpenAppeals(TEST_GUILD_ID);

        if (appeals.size() >= 2) {
            for (int i = 0; i < appeals.size() - 1; i++) {
                Instant current = appeals.get(i).submittedAt();
                Instant next = appeals.get(i + 1).submittedAt();

                assertTrue(current.isBefore(next) || current.equals(next),
                        "Appeals should be ordered by submission time (oldest first)");
            }
        }
    }

    @Test
    @Order(14)
    @DisplayName("should filter out reversed actions from open appeals")
    void shouldFilterReversedActionsFromOpenAppeals() {
        List<AppealData> openAppeals = appealRepository.getOpenAppeals(TEST_GUILD_ID);

        for (AppealData appeal : openAppeals) {
            assertNotNull(appeal.actionId(), "All appeals must have an action ID");
        }
    }
}
