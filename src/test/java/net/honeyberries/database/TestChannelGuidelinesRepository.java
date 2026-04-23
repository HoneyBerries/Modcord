package net.honeyberries.database;

import net.honeyberries.config.AppConfig;
import net.honeyberries.database.repository.ChannelGuidelinesRepository;
import net.honeyberries.datatypes.content.ChannelGuidelines;
import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import org.junit.jupiter.api.*;

import static org.junit.jupiter.api.Assertions.*;

@DisplayName("Channel Guidelines Repository Tests")
@Tag("integration")
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
public class TestChannelGuidelinesRepository {

    private static final Database database = Database.getInstance();
    private static final AppConfig appConfig = AppConfig.getInstance();
    private static final ChannelGuidelinesRepository guidelinesRepository = ChannelGuidelinesRepository.getInstance();

    // Predefined IDs
    private static final GuildID TEST_GUILD_ID = new GuildID(1488762869880324200L);
    private static final GuildID GUILD_ID_A = new GuildID(1111111111111111111L);
    private static final GuildID GUILD_ID_B = new GuildID(2222222222222222222L);
    private static final GuildID GUILD_ID_C = new GuildID(4444444444444444444L);

    private static final ChannelID TEST_CHANNEL_1_ID = new ChannelID(1488762869880324201L);
    private static final ChannelID TEST_CHANNEL_3_ID = new ChannelID(1488762869880324203L);
    private static final ChannelID NON_EXISTENT_CHANNEL_ID = new ChannelID(9999999999999999L);

    private static final ChannelID SHARED_CHANNEL_ID = new ChannelID(3333333333333333333L);
    private static final ChannelID CHANNEL_ID_A = new ChannelID(5555555555555555555L);
    private static final ChannelID CHANNEL_ID_B = new ChannelID(6666666666666666666L);

    @BeforeAll
    static void setup() {
        database.initialize(appConfig);
    }

    @Test
    @Order(1)
    @DisplayName("should successfully add new channel guidelines to database")
    void shouldAddChannelGuidelinesToDatabase() {
        String guidelinesText = "Be respectful to all members. No spam or advertising allowed.";
        ChannelGuidelines guidelines = new ChannelGuidelines(TEST_GUILD_ID, TEST_CHANNEL_1_ID, guidelinesText);

        boolean result = guidelinesRepository.addOrReplaceChannelGuidelinesToDatabase(guidelines);

        assertTrue(result, "Adding channel guidelines should succeed");
    }

    @Test
    @Order(2)
    @DisplayName("should successfully retrieve guidelines that were just added")
    void shouldRetrieveAddedChannelGuidelines() {
        String guidelinesText = "Be respectful to all members. No spam or advertising allowed.";
        ChannelGuidelines guidelines = new ChannelGuidelines(TEST_GUILD_ID, TEST_CHANNEL_1_ID, guidelinesText);

        boolean addResult = guidelinesRepository.addOrReplaceChannelGuidelinesToDatabase(guidelines);
        assertTrue(addResult, "Guidelines should be added successfully");

        ChannelGuidelines retrieved = guidelinesRepository.getChannelGuidelines(TEST_GUILD_ID, TEST_CHANNEL_1_ID);

        assertNotNull(retrieved, "Retrieved guidelines should not be null");
        assertEquals(TEST_GUILD_ID, retrieved.guildId(), "Guild ID should match");
        assertEquals(TEST_CHANNEL_1_ID, retrieved.channelId(), "Channel ID should match");
        assertEquals(guidelinesText, retrieved.guidelinesText(), "Guidelines text should match");
    }

    @Test
    @Order(3)
    @DisplayName("should replace existing guidelines with new text")
    void shouldReplaceExistingChannelGuidelines() {
        String initialText = "Initial guidelines text.";
        String replacementText = "Updated guidelines with new rules and requirements.";

        ChannelGuidelines initialGuidelines = new ChannelGuidelines(TEST_GUILD_ID, TEST_CHANNEL_3_ID, initialText);
        boolean initialResult = guidelinesRepository.addOrReplaceChannelGuidelinesToDatabase(initialGuidelines);
        assertTrue(initialResult, "Initial guidelines should be added successfully");

        ChannelGuidelines replacementGuidelines = new ChannelGuidelines(TEST_GUILD_ID, TEST_CHANNEL_3_ID, replacementText);
        boolean replaceResult = guidelinesRepository.addOrReplaceChannelGuidelinesToDatabase(replacementGuidelines);
        assertTrue(replaceResult, "Replacement should succeed");

        ChannelGuidelines retrieved = guidelinesRepository.getChannelGuidelines(TEST_GUILD_ID, TEST_CHANNEL_3_ID);

        assertNotNull(retrieved, "Retrieved guidelines should not be null");
        assertEquals(replacementText, retrieved.guidelinesText(), "Guidelines text should be replaced");
        assertNotEquals(initialText, retrieved.guidelinesText(), "Guidelines text should no longer be the initial text");
    }

    @Test
    @Order(4)
    @DisplayName("should return null when retrieving guidelines for non-existent channel in existing guild")
    void shouldReturnNullForNonExistentChannelInGuild() {
        String guidelinesText = "Guidelines for test channel.";
        ChannelGuidelines guidelines = new ChannelGuidelines(TEST_GUILD_ID, TEST_CHANNEL_1_ID, guidelinesText);
        guidelinesRepository.addOrReplaceChannelGuidelinesToDatabase(guidelines);

        ChannelGuidelines retrieved = guidelinesRepository.getChannelGuidelines(TEST_GUILD_ID, NON_EXISTENT_CHANNEL_ID);

        assertNull(retrieved, "Should return null for non-existent channel in guild");
    }

    @Test
    @Order(9)
    @DisplayName("should maintain data isolation between different guilds")
    void shouldMaintainDataIsolationBetweenGuilds() {
        String textA = "Guidelines for guild A";
        String textB = "Guidelines for guild B";

        ChannelGuidelines guidelinesA = new ChannelGuidelines(GUILD_ID_A, SHARED_CHANNEL_ID, textA);
        ChannelGuidelines guidelinesB = new ChannelGuidelines(GUILD_ID_B, SHARED_CHANNEL_ID, textB);

        guidelinesRepository.addOrReplaceChannelGuidelinesToDatabase(guidelinesA);
        guidelinesRepository.addOrReplaceChannelGuidelinesToDatabase(guidelinesB);

        ChannelGuidelines retrievedA = guidelinesRepository.getChannelGuidelines(GUILD_ID_A, SHARED_CHANNEL_ID);
        ChannelGuidelines retrievedB = guidelinesRepository.getChannelGuidelines(GUILD_ID_B, SHARED_CHANNEL_ID);

        assertNotNull(retrievedA);
        assertNotNull(retrievedB);
        assertEquals(textA, retrievedA.guidelinesText());
        assertEquals(textB, retrievedB.guidelinesText());
        assertNotEquals(retrievedA.guidelinesText(), retrievedB.guidelinesText());
    }

    @Test
    @Order(10)
    @DisplayName("should maintain data isolation between different channels in same guild")
    void shouldMaintainDataIsolationBetweenChannels() {
        String textA = "Guidelines for channel A";
        String textB = "Guidelines for channel B";

        ChannelGuidelines guidelinesA = new ChannelGuidelines(GUILD_ID_C, CHANNEL_ID_A, textA);
        ChannelGuidelines guidelinesB = new ChannelGuidelines(GUILD_ID_C, CHANNEL_ID_B, textB);

        guidelinesRepository.addOrReplaceChannelGuidelinesToDatabase(guidelinesA);
        guidelinesRepository.addOrReplaceChannelGuidelinesToDatabase(guidelinesB);

        ChannelGuidelines retrievedA = guidelinesRepository.getChannelGuidelines(GUILD_ID_C, CHANNEL_ID_A);
        ChannelGuidelines retrievedB = guidelinesRepository.getChannelGuidelines(GUILD_ID_C, CHANNEL_ID_B);

        assertNotNull(retrievedA);
        assertNotNull(retrievedB);
        assertEquals(textA, retrievedA.guidelinesText());
        assertEquals(textB, retrievedB.guidelinesText());
        assertNotEquals(retrievedA.guidelinesText(), retrievedB.guidelinesText());
    }
}
