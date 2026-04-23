package net.honeyberries.database;

import net.honeyberries.config.AppConfig;
import net.honeyberries.database.repository.GuildRulesRepository;
import net.honeyberries.datatypes.content.GuildRules;
import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import org.junit.jupiter.api.*;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Comprehensive integration tests for GuildRulesRepository.
 */
@DisplayName("Guild Rules Repository Tests")
@Tag("integration")
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
public class TestGuildRulesRepository {

    private static final Database database = Database.getInstance();
    private static final AppConfig appConfig = AppConfig.getInstance();
    private static final GuildRulesRepository rulesRepository = GuildRulesRepository.getInstance();

    /**
     * =========================
     * Centralized Test IDs
     * =========================
     */
    private static final class TestIds {

        // Guild IDs
        static final GuildID GUILD_MAIN = new GuildID(1234567890L);
        static final GuildID GUILD_LONG_TEXT = new GuildID(1234567891L);
        static final GuildID GUILD_UPDATE = new GuildID(1234567892L);
        static final GuildID GUILD_1 = new GuildID(1234567893L);
        static final GuildID GUILD_2 = new GuildID(1234567894L);
        static final GuildID GUILD_CONSISTENT = new GuildID(1234567895L);

        // Channel IDs
        static final ChannelID CHANNEL_1 = new ChannelID(1150000000000000001L);
        static final ChannelID CHANNEL_2 = new ChannelID(1150000000000000002L);
        static final ChannelID CHANNEL_UPDATE_OLD = new ChannelID(1150000000000000010L);
        static final ChannelID CHANNEL_UPDATE_NEW = new ChannelID(1150000000000000011L);
        static final ChannelID CHANNEL_MULTI_1 = new ChannelID(1150000000000000030L);
        static final ChannelID CHANNEL_MULTI_2 = new ChannelID(1150000000000000031L);
        static final ChannelID CHANNEL_CONSISTENT = new ChannelID(1150000000000000040L);
    }

    @BeforeAll
    static void setup() {
        database.initialize(appConfig);
    }

    @Test
    @Order(1)
    @DisplayName("should add new rules to database successfully")
    void shouldAddNewRulesToDatabase() {
        String rulesText = "1. Be respectful to all members\n2. No spam\n3. No NSFW content";
        GuildRules guildRules = new GuildRules(TestIds.GUILD_MAIN, TestIds.CHANNEL_1, rulesText);

        boolean result = rulesRepository.addOrReplaceGuildRulesToDatabase(guildRules);

        assertTrue(result);
    }

    @Test
    @Order(2)
    @DisplayName("should retrieve added rules from cache")
    void shouldRetrieveAddedRulesFromCache() {
        GuildRules rules = rulesRepository.getGuildRulesFromCache(TestIds.GUILD_MAIN);

        assertNotNull(rules);
        assertEquals(TestIds.GUILD_MAIN, rules.guildId());
        assertEquals(TestIds.CHANNEL_1, rules.rulesChannelId());
        assertEquals("1. Be respectful to all members\n2. No spam\n3. No NSFW content", rules.rulesText());
    }

    @Test
    @Order(3)
    @DisplayName("should replace existing rules successfully")
    void shouldReplaceExistingRules() {
        String newRulesText = "Updated rules:\n1. Be nice\n2. Have fun\n3. Follow Discord ToS";
        GuildRules updatedRules = new GuildRules(TestIds.GUILD_MAIN, TestIds.CHANNEL_2, newRulesText);

        boolean result = rulesRepository.addOrReplaceGuildRulesToDatabase(updatedRules);

        assertTrue(result);
    }

    @Test
    @Order(4)
    @DisplayName("should retrieve updated rules from cache")
    void shouldRetrieveUpdatedRulesFromCache() {
        GuildRules rules = rulesRepository.getGuildRulesFromCache(TestIds.GUILD_MAIN);

        assertNotNull(rules);
        assertEquals(TestIds.GUILD_MAIN, rules.guildId());
        assertEquals(TestIds.CHANNEL_2, rules.rulesChannelId());
        assertEquals("Updated rules:\n1. Be nice\n2. Have fun\n3. Follow Discord ToS", rules.rulesText());
    }

    @Test
    @Order(5)
    @DisplayName("should return null for non-existent guild rules")
    void shouldReturnNullForNonExistentGuildRules() {
        GuildID nonExistentGuildId = new GuildID(8888888888888888777L);

        GuildRules rules = rulesRepository.getGuildRulesFromCache(nonExistentGuildId);

        assertNull(rules);
    }

    @Test
    @Order(6)
    @DisplayName("should handle long rules text with special characters")
    void shouldHandleLongRulesTextWithSpecialCharacters() {
        String longRulesText = """
                Rules & Regulations (v1.0)

                1. Respect: We expect all members to treat each other with courtesy.
                2. No Spam: Don't post repetitive or irrelevant content.
                3. No NSFW: Keep the server family-friendly.
                4. Follow ToS: Adhere to Discord's Terms of Service.

                Special characters: !@#$%^&*()_+-=[]{}|;':,./<>?
                Unicode support: 你好, مرحبا, שלום, здравствуй

                Questions? Contact moderators.
                """;

        GuildRules rulesWithLongText = new GuildRules(TestIds.GUILD_LONG_TEXT, TestIds.CHANNEL_1, longRulesText);

        boolean result = rulesRepository.addOrReplaceGuildRulesToDatabase(rulesWithLongText);

        assertTrue(result);
    }

    @Test
    @Order(7)
    @DisplayName("should retrieve long rules text with special characters from cache")
    void shouldRetrieveLongRulesTextWithSpecialCharactersFromCache() {
        GuildRules rules = rulesRepository.getGuildRulesFromCache(TestIds.GUILD_LONG_TEXT);

        assertNotNull(rules);
        assertNotNull(rules.rulesText());
        assertTrue(rules.rulesText().contains("Respect"));
        assertTrue(rules.rulesText().contains("你好"));
    }

    @Test
    @Order(8)
    @DisplayName("should preserve exact channel ID when updating rules")
    void shouldPreserveExactChannelIdWhenUpdating() {
        GuildRules originalRules = new GuildRules(TestIds.GUILD_UPDATE, TestIds.CHANNEL_UPDATE_OLD, "Original text");
        rulesRepository.addOrReplaceGuildRulesToDatabase(originalRules);

        GuildRules updatedRules = new GuildRules(TestIds.GUILD_UPDATE, TestIds.CHANNEL_UPDATE_NEW, "Updated text");
        boolean result = rulesRepository.addOrReplaceGuildRulesToDatabase(updatedRules);

        assertTrue(result);

        GuildRules retrieved = rulesRepository.getGuildRulesFromCache(TestIds.GUILD_UPDATE);
        assertNotNull(retrieved);
        assertEquals(TestIds.CHANNEL_UPDATE_NEW, retrieved.rulesChannelId());
        assertEquals("Updated text", retrieved.rulesText());
    }

    @Test
    @Order(9)
    @DisplayName("should support multiple guild rules independently")
    void shouldSupportMultipleGuildRulesIndependently() {
        GuildRules guildRules1 = new GuildRules(TestIds.GUILD_1, TestIds.CHANNEL_MULTI_1, "Guild 1 rules");
        GuildRules guildRules2 = new GuildRules(TestIds.GUILD_2, TestIds.CHANNEL_MULTI_2, "Guild 2 rules");

        boolean result1 = rulesRepository.addOrReplaceGuildRulesToDatabase(guildRules1);
        boolean result2 = rulesRepository.addOrReplaceGuildRulesToDatabase(guildRules2);

        assertTrue(result1 && result2);

        GuildRules retrieved1 = rulesRepository.getGuildRulesFromCache(TestIds.GUILD_1);
        GuildRules retrieved2 = rulesRepository.getGuildRulesFromCache(TestIds.GUILD_2);

        assertNotNull(retrieved1);
        assertNotNull(retrieved2);

        assertEquals("Guild 1 rules", retrieved1.rulesText());
        assertEquals("Guild 2 rules", retrieved2.rulesText());
        assertEquals(TestIds.CHANNEL_MULTI_1, retrieved1.rulesChannelId());
        assertEquals(TestIds.CHANNEL_MULTI_2, retrieved2.rulesChannelId());
    }

    @Test
    @Order(10)
    @DisplayName("should return consistent results on repeated retrieval")
    void shouldReturnConsistentResultsOnRepeatedRetrieval() {
        GuildRules guildRules = new GuildRules(TestIds.GUILD_CONSISTENT, TestIds.CHANNEL_CONSISTENT, "Consistent rules");
        rulesRepository.addOrReplaceGuildRulesToDatabase(guildRules);

        GuildRules retrieved1 = rulesRepository.getGuildRulesFromCache(TestIds.GUILD_CONSISTENT);
        GuildRules retrieved2 = rulesRepository.getGuildRulesFromCache(TestIds.GUILD_CONSISTENT);
        GuildRules retrieved3 = rulesRepository.getGuildRulesFromCache(TestIds.GUILD_CONSISTENT);

        assertNotNull(retrieved1);
        assertNotNull(retrieved2);
        assertNotNull(retrieved3);

        assertEquals(retrieved1.guildId(), retrieved2.guildId());
        assertEquals(retrieved1.guildId(), retrieved3.guildId());

        assertEquals(retrieved1.rulesChannelId(), retrieved2.rulesChannelId());
        assertEquals(retrieved1.rulesChannelId(), retrieved3.rulesChannelId());

        assertEquals(retrieved1.rulesText(), retrieved2.rulesText());
        assertEquals(retrieved1.rulesText(), retrieved3.rulesText());
    }
}
