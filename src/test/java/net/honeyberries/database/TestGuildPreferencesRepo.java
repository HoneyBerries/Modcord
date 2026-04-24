package net.honeyberries.database;

import net.honeyberries.config.AppConfig;
import net.honeyberries.database.repository.GuildPreferencesRepository;
import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.preferences.GuildPreferences;
import org.junit.jupiter.api.*;

import static org.junit.jupiter.api.Assertions.*;

@DisplayName("Guild Preferences Repo Tests")
public class TestGuildPreferencesRepo {

    private static final Database database = Database.getInstance();
    private final GuildPreferencesRepository repository = GuildPreferencesRepository.getInstance();
    
    private static final GuildID TEST_GUILD_ID = new GuildID(123456789L);
    private static final ChannelID TEST_CHANNEL_ID = new ChannelID(987654321L);

    @BeforeAll
    static void setup() {
        database.initialize(AppConfig.getInstance());
    }

    @AfterEach
    void cleanup() {
        repository.deleteGuildPreferences(TEST_GUILD_ID);
    }

    @Test
    @DisplayName("Should insert and retrieve guild preferences")
    void shouldInsertAndRetrieve() {
        GuildPreferences prefs = new GuildPreferences.Builder(TEST_GUILD_ID)
                .aiEnabled(true)
                .rulesChannelId(TEST_CHANNEL_ID)
                .auditLogChannelId(TEST_CHANNEL_ID)
                .autoWarnEnabled(false)
                .build();

        boolean success = repository.addOrUpdateGuildPreferences(prefs);
        assertTrue(success, "Insert should be successful");

        GuildPreferences retrieved = repository.getGuildPreferences(TEST_GUILD_ID);
        assertNotNull(retrieved, "Retrieved preferences should not be null");
        assertEquals(TEST_GUILD_ID, retrieved.guildId());
        assertTrue(retrieved.aiEnabled());
        assertEquals(TEST_CHANNEL_ID, retrieved.rulesChannelID());
        assertEquals(TEST_CHANNEL_ID, retrieved.auditLogChannelId());
        assertFalse(retrieved.autoWarnEnabled());
    }

    @Test
    @DisplayName("Should handle null channel IDs")
    void shouldHandleNullChannels() {
        GuildPreferences prefs = GuildPreferences.defaults(TEST_GUILD_ID);
        repository.addOrUpdateGuildPreferences(prefs);

        GuildPreferences retrieved = repository.getGuildPreferences(TEST_GUILD_ID);
        assertNotNull(retrieved);
        assertNull(retrieved.rulesChannelID(), "Rules channel should be null by default");
        assertNull(retrieved.auditLogChannelId(), "Audit log channel should be null by default");
    }

    @Test
    @DisplayName("Should upsert guild preferences")
    void shouldUpsert() {
        // First insert
        GuildPreferences prefs1 = GuildPreferences.defaults(TEST_GUILD_ID);
        repository.addOrUpdateGuildPreferences(prefs1);

        // Update
        GuildPreferences prefs2 = prefs1.toBuilder()
                .aiEnabled(false)
                .autoBanEnabled(false)
                .build();

        boolean success = repository.addOrUpdateGuildPreferences(prefs2);
        assertTrue(success, "Update should be successful");

        GuildPreferences retrieved = repository.getGuildPreferences(TEST_GUILD_ID);
        assertNotNull(retrieved);
        assertFalse(retrieved.aiEnabled(), "AI should be disabled after update");
        assertFalse(retrieved.autoBanEnabled(), "Auto-ban should be disabled after update");
    }

    @Test
    @DisplayName("Should return null for non-existent guild")
    void shouldReturnNullForMissingGuild() {
        GuildID nonExistent = new GuildID(999999999L);
        GuildPreferences retrieved = repository.getGuildPreferences(nonExistent);
        assertNull(retrieved, "Should return null for a guild that doesn't exist");
    }
}
