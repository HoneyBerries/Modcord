package net.honeyberries.database;

import net.honeyberries.config.AppConfig;
import net.honeyberries.database.repository.ExcludedEntitiesRepository;
import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.discord.RoleID;
import net.honeyberries.datatypes.discord.UserID;
import org.junit.jupiter.api.*;

import static org.junit.jupiter.api.Assertions.*;

@DisplayName("Excluded Entities Repo Tests")
public class TestExcludedEntitiesRepo {

    private static final Database database = Database.getInstance();
    private final ExcludedEntitiesRepository repository = ExcludedEntitiesRepository.getInstance();
    
    private static final GuildID TEST_GUILD_ID = new GuildID(123456789L);
    private static final UserID TEST_USER_ID = new UserID(111L);
    private static final RoleID TEST_ROLE_ID = new RoleID(222L);
    private static final ChannelID TEST_CHANNEL_ID = new ChannelID(333L);

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
            try (var ps = conn.prepareStatement("DELETE FROM guild_moderation_exemptions WHERE guild_id = ?")) {
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
    @DisplayName("Should mark and check excluded user")
    void shouldExcludeUser() {
        assertTrue(repository.markExcluded(TEST_GUILD_ID, TEST_USER_ID));
        assertTrue(repository.isExcluded(TEST_GUILD_ID, TEST_USER_ID));
        
        repository.unmarkExcluded(TEST_GUILD_ID, TEST_USER_ID);
        assertFalse(repository.isExcluded(TEST_GUILD_ID, TEST_USER_ID));
    }

    @Test
    @DisplayName("Should mark and check excluded role")
    void shouldExcludeRole() {
        assertTrue(repository.markExcluded(TEST_GUILD_ID, TEST_ROLE_ID));
        assertTrue(repository.isExcluded(TEST_GUILD_ID, TEST_ROLE_ID));
        
        repository.unmarkExcluded(TEST_GUILD_ID, TEST_ROLE_ID);
        assertFalse(repository.isExcluded(TEST_GUILD_ID, TEST_ROLE_ID));
    }

    @Test
    @DisplayName("Should mark and check excluded channel")
    void shouldExcludeChannel() {
        assertTrue(repository.markExcluded(TEST_GUILD_ID, TEST_CHANNEL_ID));
        assertTrue(repository.isExcluded(TEST_GUILD_ID, TEST_CHANNEL_ID));
        
        repository.unmarkExcluded(TEST_GUILD_ID, TEST_CHANNEL_ID);
        assertFalse(repository.isExcluded(TEST_GUILD_ID, TEST_CHANNEL_ID));
    }

    @Test
    @DisplayName("Should return empty entities for no exclusions")
    void shouldReturnEmptyForNoExclusions() {
        var entities = repository.getExcludedEntities(TEST_GUILD_ID);
        assertTrue(entities.userIDs().isEmpty());
        assertTrue(entities.roleIDs().isEmpty());
        assertTrue(entities.channelIDs().isEmpty());
    }
}
