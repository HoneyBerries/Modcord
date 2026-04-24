package net.honeyberries.database;

import net.honeyberries.config.AppConfig;
import net.honeyberries.database.repository.AppealRepository;
import net.honeyberries.database.repository.GuildModerationActionsRepository;
import net.honeyberries.datatypes.action.ActionType;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.discord.UserID;
import org.junit.jupiter.api.*;

import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;

@DisplayName("Appeal Repo Tests")
public class TestAppealRepo {

    private static final Database database = Database.getInstance();
    private final AppealRepository repository = AppealRepository.getInstance();
    private final GuildModerationActionsRepository actionsRepository = new GuildModerationActionsRepository();
    
    private static final GuildID TEST_GUILD_ID = new GuildID(123456789L);
    private static final UserID TEST_USER_ID = new UserID(111L);
    private static final UserID MOD_USER_ID = new UserID(999L);
    private static final UUID ACTION_ID = UUID.randomUUID();

    @BeforeAll
    static void setup() {
        database.initialize(AppConfig.getInstance());
    }

    @BeforeEach
    void setupBaseData() {
        database.transaction(conn -> {
            try (var ps = conn.prepareStatement("INSERT INTO guild_preferences (guild_id) VALUES (?) ON CONFLICT DO NOTHING")) {
                ps.setLong(1, TEST_GUILD_ID.value());
                ps.executeUpdate();
            }
            // Insert dummy action to link appeal to
            try (var ps = conn.prepareStatement("INSERT INTO guild_moderation_actions (action_id, guild_id, user_id, moderator_id, action, reason) VALUES (?, ?, ?, ?, ?, ?)")) {
                ps.setObject(1, ACTION_ID);
                ps.setLong(2, TEST_GUILD_ID.value());
                ps.setLong(3, TEST_USER_ID.value());
                ps.setLong(4, MOD_USER_ID.value());
                ps.setString(5, ActionType.WARN.name());
                ps.setString(6, "Initial warn");
                ps.executeUpdate();
            }
        });
    }

    @AfterEach
    void cleanup() {
        database.transaction(conn -> {
            try (var ps = conn.prepareStatement("DELETE FROM moderation_appeals WHERE guild_id = ?")) {
                ps.setLong(1, TEST_GUILD_ID.value());
                ps.executeUpdate();
            }
            try (var ps = conn.prepareStatement("DELETE FROM guild_moderation_actions WHERE guild_id = ?")) {
                ps.setLong(1, TEST_GUILD_ID.value());
                ps.executeUpdate();
            }
            try (var ps = conn.prepareStatement("DELETE FROM guild_preferences WHERE guild_id = ?")) {
                ps.setLong(1, TEST_GUILD_ID.value());
                ps.executeUpdate();
            }
        });
    }

    @Test
    @DisplayName("Should create and close an appeal")
    void shouldCreateAndCloseAppeal() {
        UUID appealId = repository.createAppeal(TEST_GUILD_ID, TEST_USER_ID, ACTION_ID, "Unfair warning");
        assertNotNull(appealId);

        var appeals = repository.getOpenAppeals(TEST_GUILD_ID);
        assertEquals(1, appeals.size());
        
        boolean closed = repository.closeAppeal(TEST_GUILD_ID, appealId, "Resolved as valid");
        assertTrue(closed);
        
        assertTrue(repository.getOpenAppeals(TEST_GUILD_ID).isEmpty());
    }
}
