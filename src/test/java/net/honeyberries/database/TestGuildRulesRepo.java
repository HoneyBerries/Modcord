package net.honeyberries.database;

import net.honeyberries.config.AppConfig;
import net.honeyberries.database.repository.GuildRulesRepository;
import net.honeyberries.datatypes.content.GuildRules;
import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import org.junit.jupiter.api.*;

import static org.junit.jupiter.api.Assertions.*;

@DisplayName("Guild Rules Repo Tests")
public class TestGuildRulesRepo {

    private static final Database database = Database.getInstance();
    private final GuildRulesRepository repository = GuildRulesRepository.getInstance();
    
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
            try (var ps = conn.prepareStatement("DELETE FROM guild_rules WHERE guild_id = ?")) {
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
    @DisplayName("Should insert and retrieve guild rules")
    void shouldInsertAndRetrieve() {
        GuildRules rules = new GuildRules(TEST_GUILD_ID, TEST_CHANNEL_ID, "Rule 1: Be nice.");
        
        boolean success = repository.addOrReplaceGuildRulesToDatabase(rules);
        assertTrue(success, "Insert should be successful");

        GuildRules retrieved = repository.getGuildRulesFromCache(TEST_GUILD_ID);
        assertNotNull(retrieved);
        assertEquals(TEST_GUILD_ID, retrieved.guildId());
        assertEquals(TEST_CHANNEL_ID, retrieved.rulesChannelId());
        assertEquals("Rule 1: Be nice.", retrieved.rulesText());
    }

    @Test
    @DisplayName("Should upsert guild rules")
    void shouldUpsert() {
        GuildRules rules1 = new GuildRules(TEST_GUILD_ID, TEST_CHANNEL_ID, "Initial rules");
        repository.addOrReplaceGuildRulesToDatabase(rules1);

        GuildRules rules2 = new GuildRules(TEST_GUILD_ID, null, "Updated rules");
        repository.addOrReplaceGuildRulesToDatabase(rules2);

        GuildRules retrieved = repository.getGuildRulesFromCache(TEST_GUILD_ID);
        assertNotNull(retrieved);
        assertNull(retrieved.rulesChannelId(), "Channel should be null after update");
        assertEquals("Updated rules", retrieved.rulesText());
    }

    @Test
    @DisplayName("Should return null for non-existent guild rules")
    void shouldReturnNullForMissingGuild() {
        GuildID nonExistent = new GuildID(999999999L);
        GuildRules retrieved = repository.getGuildRulesFromCache(nonExistent);
        assertNull(retrieved);
    }
}
