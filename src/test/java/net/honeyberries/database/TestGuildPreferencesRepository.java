package net.honeyberries.database;

import net.honeyberries.config.AppConfig;
import net.honeyberries.database.repository.GuildPreferencesRepository;
import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.preferences.GuildPreferences;
import org.junit.jupiter.api.*;

import java.util.Objects;

import static org.junit.jupiter.api.Assertions.*;

@DisplayName("Guild Preferences Repository Tests")
@Tag("integration")
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
public class TestGuildPreferencesRepository {

    private static final Database database = Database.getInstance();
    private static final AppConfig appConfig = AppConfig.getInstance();
    private static final GuildPreferencesRepository repository = GuildPreferencesRepository.getInstance();

    /**
     * =========================
     * Centralized Test IDs
     * =========================
     */
    private static final class TestIds {

        // Guilds
        static final GuildID GUILD_MAIN = new GuildID(1488762869880324200L);
        static final GuildID GUILD_SECOND = new GuildID(1488762869880324201L);
        static final GuildID TEMP_1 = new GuildID(1488762869880324202L);
        static final GuildID TEMP_2 = new GuildID(1488762869880324203L);
        static final GuildID TEMP_3 = new GuildID(1488762869880324204L);
        static final GuildID TEMP_4 = new GuildID(1488762869880324205L);
        static final GuildID TEMP_5 = new GuildID(1488762869880324206L);
        static final GuildID TEMP_6 = new GuildID(1488762869880324207L);
        static final GuildID TEMP_7 = new GuildID(1488762869880324208L);

        // Channels
        static final ChannelID RULES_1 = new ChannelID(1234567890123456789L);
        static final ChannelID AUDIT_1 = new ChannelID(9876543210L);
        static final ChannelID RULES_2 = new ChannelID(1111111111111111111L);
        static final ChannelID AUDIT_2 = new ChannelID(2222222222222222222L);
    }

    @BeforeAll
    static void setup() {
        database.initialize(appConfig);
    }

    @Test @Order(1)
    void shouldCreateAndRetrievePreferences() {
        GuildPreferences prefs = new GuildPreferences(
                TestIds.GUILD_MAIN,
                true,
                TestIds.RULES_1,
                true,
                true,
                true,
                true,
                true,
                TestIds.AUDIT_1
        );

        assertTrue(repository.addOrUpdateGuildPreferences(prefs));

        GuildPreferences retrieved = repository.getGuildPreferences(TestIds.GUILD_MAIN);
        assertNotNull(retrieved);
        assertEquals(TestIds.RULES_1, retrieved.rulesChannelID());
        assertEquals(TestIds.AUDIT_1, retrieved.auditLogChannelId());
    }

    @Test @Order(2)
    void shouldHandleNullChannels() {
        GuildPreferences prefs = new GuildPreferences(
                TestIds.GUILD_SECOND,
                true,
                null,
                true,
                false,
                true,
                false,
                true,
                null
        );

        repository.addOrUpdateGuildPreferences(prefs);

        GuildPreferences retrieved = repository.getGuildPreferences(TestIds.GUILD_SECOND);
        assert retrieved != null;
        assertNull(retrieved.rulesChannelID());
        assertNull(retrieved.auditLogChannelId());
    }

    @Test @Order(3)
    void shouldUpdatePreferences() {
        GuildPreferences updated = new GuildPreferences(
                TestIds.GUILD_MAIN,
                false,
                TestIds.RULES_2,
                false,
                false,
                false,
                false,
                false,
                TestIds.AUDIT_2
        );

        assertTrue(repository.addOrUpdateGuildPreferences(updated));

        GuildPreferences retrieved = repository.getGuildPreferences(TestIds.GUILD_MAIN);
        assert retrieved != null;
        assertFalse(retrieved.aiEnabled());
        assertEquals(TestIds.RULES_2, retrieved.rulesChannelID());
    }

    @Test @Order(4)
    void shouldDeletePreferences() {
        repository.deleteGuildPreferences(TestIds.GUILD_SECOND);
        assertNull(repository.getGuildPreferences(TestIds.GUILD_SECOND));
    }

    @Test @Order(5)
    void shouldHandleNullToValueTransition() {
        GuildPreferences initial = new GuildPreferences(
                TestIds.TEMP_1,
                true,
                null,
                true,
                true,
                true,
                true,
                true,
                null
        );

        repository.addOrUpdateGuildPreferences(initial);

        GuildPreferences updated = initial
                .withRulesChannelId(TestIds.RULES_1)
                .withAuditLogChannelId(TestIds.AUDIT_1);

        repository.addOrUpdateGuildPreferences(updated);

        GuildPreferences retrieved = repository.getGuildPreferences(TestIds.TEMP_1);
        assert retrieved != null;
        assertEquals(TestIds.RULES_1, retrieved.rulesChannelID());
        assertEquals(TestIds.AUDIT_1, retrieved.auditLogChannelId());

        repository.deleteGuildPreferences(TestIds.TEMP_1);
    }

    @Test @Order(6)
    void shouldHandleValueToNullTransition() {
        GuildPreferences initial = new GuildPreferences(
                TestIds.TEMP_2,
                true,
                TestIds.RULES_1,
                true,
                true,
                true,
                true,
                true,
                TestIds.AUDIT_1
        );

        repository.addOrUpdateGuildPreferences(initial);

        GuildPreferences updated = initial
                .withRulesChannelId(null)
                .withAuditLogChannelId(null);

        repository.addOrUpdateGuildPreferences(updated);

        GuildPreferences retrieved = repository.getGuildPreferences(TestIds.TEMP_2);
        assert retrieved != null;
        assertNull(retrieved.rulesChannelID());
        assertNull(retrieved.auditLogChannelId());

        repository.deleteGuildPreferences(TestIds.TEMP_2);
    }

    @Test @Order(7)
    void shouldHandleBooleanExtremes() {
        GuildPreferences allFalse = new GuildPreferences(
                TestIds.TEMP_3,
                false,
                null,
                false,
                false,
                false,
                false,
                false,
                null
        );

        repository.addOrUpdateGuildPreferences(allFalse);
        assertFalse(Objects.requireNonNull(repository.getGuildPreferences(TestIds.TEMP_3)).aiEnabled());

        GuildPreferences allTrue = new GuildPreferences(
                TestIds.TEMP_3,
                true,
                TestIds.RULES_1,
                true,
                true,
                true,
                true,
                true,
                TestIds.AUDIT_1
        );

        repository.addOrUpdateGuildPreferences(allTrue);
        assertTrue(Objects.requireNonNull(repository.getGuildPreferences(TestIds.TEMP_3)).aiEnabled());

        repository.deleteGuildPreferences(TestIds.TEMP_3);
    }

    @Test @Order(8)
    void shouldPreserveChannelsWhenUpdatingBooleans() {
        GuildPreferences initial = new GuildPreferences(
                TestIds.TEMP_4,
                true,
                TestIds.RULES_1,
                true,
                true,
                true,
                true,
                true,
                TestIds.AUDIT_1
        );

        repository.addOrUpdateGuildPreferences(initial);

        GuildPreferences updated = initial
                .withAiEnabled(false)
                .withAutoWarnEnabled(false);

        repository.addOrUpdateGuildPreferences(updated);

        GuildPreferences retrieved = repository.getGuildPreferences(TestIds.TEMP_4);
        assert retrieved != null;
        assertEquals(TestIds.RULES_1, retrieved.rulesChannelID());
        assertEquals(TestIds.AUDIT_1, retrieved.auditLogChannelId());

        repository.deleteGuildPreferences(TestIds.TEMP_4);
    }

    @Test @Order(9)
    void shouldHandleSequentialUpdates() {
        GuildPreferences prefs = GuildPreferences.defaults(TestIds.TEMP_5);
        repository.addOrUpdateGuildPreferences(prefs);

        prefs = prefs.withAiEnabled(false);
        repository.addOrUpdateGuildPreferences(prefs);

        prefs = prefs.withAutoWarnEnabled(false);
        repository.addOrUpdateGuildPreferences(prefs);

        GuildPreferences retrieved = repository.getGuildPreferences(TestIds.TEMP_5);
        assert retrieved != null;
        assertFalse(retrieved.aiEnabled());
        assertFalse(retrieved.autoWarnEnabled());

        repository.deleteGuildPreferences(TestIds.TEMP_5);
    }

    @Test @Order(10)
    void shouldUseDefaultsFactory() {
        GuildPreferences prefs = GuildPreferences.defaults(TestIds.TEMP_6);
        repository.addOrUpdateGuildPreferences(prefs);

        GuildPreferences retrieved = repository.getGuildPreferences(TestIds.TEMP_6);
        assert retrieved != null;
        assertTrue(retrieved.aiEnabled());

        repository.deleteGuildPreferences(TestIds.TEMP_6);
    }

    @Test @Order(11)
    void shouldUseBuilder() {
        GuildPreferences prefs = new GuildPreferences.Builder(TestIds.TEMP_7)
                .aiEnabled(true)
                .rulesChannelId(TestIds.RULES_1)
                .autoWarnEnabled(true)
                .autoDeleteEnabled(true)
                .autoTimeoutEnabled(true)
                .autoKickEnabled(true)
                .autoBanEnabled(true)
                .auditLogChannelId(TestIds.AUDIT_1)
                .build();

        repository.addOrUpdateGuildPreferences(prefs);

        GuildPreferences retrieved = repository.getGuildPreferences(TestIds.TEMP_7);
        assert retrieved != null;
        assertEquals(TestIds.RULES_1, retrieved.rulesChannelID());

        repository.deleteGuildPreferences(TestIds.TEMP_7);
    }
}
