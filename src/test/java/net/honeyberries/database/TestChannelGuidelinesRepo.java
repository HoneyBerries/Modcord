package net.honeyberries.database;

import net.honeyberries.config.AppConfig;
import net.honeyberries.database.repository.ChannelGuidelinesRepository;
import net.honeyberries.datatypes.content.ChannelGuidelines;
import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import org.junit.jupiter.api.*;

import static org.junit.jupiter.api.Assertions.*;

@DisplayName("Channel Guidelines Repo Tests")
public class TestChannelGuidelinesRepo {

    private static final Database database = Database.getInstance();
    private final ChannelGuidelinesRepository repository = ChannelGuidelinesRepository.getInstance();
    
    private static final GuildID TEST_GUILD_ID = new GuildID(123456789L);
    private static final ChannelID TEST_CHANNEL_ID = new ChannelID(987654321L);

    @BeforeAll
    static void setup() {
        database.initialize(AppConfig.getInstance());
    }

    @BeforeEach
    void setupGuild() {
        database.transaction(conn -> {
            try (var ps = conn.prepareStatement("INSERT INTO guild_preferences (guild_id) VALUES (?) ON CONFLICT DO NOTHING")) {
                ps.setLong(1, TEST_GUILD_ID.value());
                ps.executeUpdate();
            }
        });
    }

    @AfterEach
    void cleanup() {
        database.transaction(conn -> {
            try (var ps = conn.prepareStatement("DELETE FROM guild_channel_guidelines WHERE guild_id = ?")) {
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
    @DisplayName("Should insert and retrieve channel guidelines")
    void shouldInsertAndRetrieve() {
        ChannelGuidelines guidelines = new ChannelGuidelines(TEST_GUILD_ID, TEST_CHANNEL_ID, "No spam.");
        
        boolean success = repository.addOrReplaceChannelGuidelinesToDatabase(guidelines);
        assertTrue(success, "Insert should be successful");

        ChannelGuidelines retrieved = repository.getChannelGuidelines(TEST_GUILD_ID, TEST_CHANNEL_ID);
        assertNotNull(retrieved);
        assertEquals("No spam.", retrieved.guidelinesText());
    }

    @Test
    @DisplayName("Should upsert channel guidelines")
    void shouldUpsert() {
        repository.addOrReplaceChannelGuidelinesToDatabase(new ChannelGuidelines(TEST_GUILD_ID, TEST_CHANNEL_ID, "Old"));
        repository.addOrReplaceChannelGuidelinesToDatabase(new ChannelGuidelines(TEST_GUILD_ID, TEST_CHANNEL_ID, "New"));

        ChannelGuidelines retrieved = repository.getChannelGuidelines(TEST_GUILD_ID, TEST_CHANNEL_ID);
        assertNotNull(retrieved);
        assertEquals("New", retrieved.guidelinesText());
    }

    @Test
    @DisplayName("Should return null for non-existent guidelines")
    void shouldReturnNullForMissing() {
        ChannelGuidelines retrieved = repository.getChannelGuidelines(TEST_GUILD_ID, new ChannelID(0L));
        assertNull(retrieved);
    }
}
