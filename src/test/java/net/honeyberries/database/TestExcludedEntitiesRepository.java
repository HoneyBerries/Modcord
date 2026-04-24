package net.honeyberries.database;

import net.honeyberries.database.repository.ExcludedEntitiesRepository;
import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.discord.RoleID;
import net.honeyberries.datatypes.discord.UserID;
import org.junit.jupiter.api.*;

import static org.junit.jupiter.api.Assertions.*;

@DisplayName("Excluded Entities Repository Tests")
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
public class TestExcludedEntitiesRepository extends DatabaseIntegrationTest {

    private static final ExcludedEntitiesRepository repository = ExcludedEntitiesRepository.getInstance();

    private static final class TestIds {
        // Guilds
        static final GuildID MAIN_GUILD = new GuildID(1488762869880324200L);
        static final GuildID EMPTY_GUILD = new GuildID(8000000000000000000L);
        static final GuildID SECOND_GUILD = new GuildID(8000000000000000001L);

        // Users
        static final UserID USER_1 = new UserID(1104649796821729320L);
        static final UserID USER_2 = new UserID(1180022370375835731L);
        static final UserID USER_3 = new UserID(1260476582519242767L);

        // Roles
        static final RoleID ROLE_1 = new RoleID(1234567890123456789L);
        static final RoleID ROLE_2 = new RoleID(9876543210L);
        static final RoleID ROLE_3 = new RoleID(5555555555555555555L);

        // Channels
        static final ChannelID CHANNEL_1 = new ChannelID(1111111111111111111L);
        static final ChannelID CHANNEL_2 = new ChannelID(2222222222222222222L);
        static final ChannelID CHANNEL_3 = new ChannelID(3333333333333333333L);
    }

    @BeforeEach
    void cleanupTestData() {
        deleteFromTable("guild_moderation_exemptions", "guild_id = ?", TestIds.MAIN_GUILD.value());
        deleteFromTable("guild_moderation_exemptions", "guild_id = ?", TestIds.SECOND_GUILD.value());
    }

    @Test @Order(1)
    void shouldMarkAndVerifyUserExcluded() {
        assertTrue(repository.markExcluded(TestIds.MAIN_GUILD, TestIds.USER_1));
        assertTrue(repository.isExcluded(TestIds.MAIN_GUILD, TestIds.USER_1));
    }

    @Test @Order(2)
    void shouldVerifyUnmarkedUserNotExcluded() {
        assertFalse(repository.isExcluded(TestIds.MAIN_GUILD, TestIds.USER_3));
    }

    @Test @Order(3)
    void shouldUnmarkUser() {
        repository.markExcluded(TestIds.MAIN_GUILD, TestIds.USER_1);
        repository.unmarkExcluded(TestIds.MAIN_GUILD, TestIds.USER_1);
        assertFalse(repository.isExcluded(TestIds.MAIN_GUILD, TestIds.USER_1));
    }

    @Test @Order(4)
    void shouldBeIdempotentMark() {
        repository.markExcluded(TestIds.MAIN_GUILD, TestIds.USER_1);
        assertTrue(repository.markExcluded(TestIds.MAIN_GUILD, TestIds.USER_1));
    }

    @Test @Order(5)
    void shouldMarkAndVerifyRoleExcluded() {
        assertTrue(repository.markExcluded(TestIds.MAIN_GUILD, TestIds.ROLE_1));
        assertTrue(repository.isExcluded(TestIds.MAIN_GUILD, TestIds.ROLE_1));
    }

    @Test @Order(6)
    void shouldVerifyUnmarkedRoleNotExcluded() {
        assertFalse(repository.isExcluded(TestIds.MAIN_GUILD, TestIds.ROLE_3));
    }

    @Test @Order(7)
    void shouldMarkAndVerifyChannelExcluded() {
        assertTrue(repository.markExcluded(TestIds.MAIN_GUILD, TestIds.CHANNEL_1));
        assertTrue(repository.isExcluded(TestIds.MAIN_GUILD, TestIds.CHANNEL_1));
    }

    @Test @Order(8)
    void shouldVerifyUnmarkedChannelNotExcluded() {
        assertFalse(repository.isExcluded(TestIds.MAIN_GUILD, TestIds.CHANNEL_3));
    }

    @Test @Order(10)
    void shouldReturnEmptyForNewGuild() {
        var entities = repository.getExcludedEntities(TestIds.EMPTY_GUILD);
        assertTrue(entities.userIDs().isEmpty());
        assertTrue(entities.roleIDs().isEmpty());
        assertTrue(entities.channelIDs().isEmpty());
    }

    @Test @Order(11)
    void shouldReturnAllExcludedEntitiesAndBeImmutable() {
        repository.markExcluded(TestIds.MAIN_GUILD, TestIds.USER_1);
        repository.markExcluded(TestIds.MAIN_GUILD, TestIds.USER_2);
        repository.markExcluded(TestIds.MAIN_GUILD, TestIds.ROLE_1);
        repository.markExcluded(TestIds.MAIN_GUILD, TestIds.ROLE_2);
        repository.markExcluded(TestIds.MAIN_GUILD, TestIds.CHANNEL_1);

        var entities = repository.getExcludedEntities(TestIds.MAIN_GUILD);

        assertTrue(entities.userIDs().contains(TestIds.USER_1));
        assertTrue(entities.userIDs().contains(TestIds.USER_2));
        assertTrue(entities.roleIDs().contains(TestIds.ROLE_1));
        assertTrue(entities.roleIDs().contains(TestIds.ROLE_2));
        assertTrue(entities.channelIDs().contains(TestIds.CHANNEL_1));

        // Verify immutability
        assertThrows(UnsupportedOperationException.class, () -> entities.userIDs().add(new UserID(1)));
        assertThrows(UnsupportedOperationException.class, () -> entities.roleIDs().add(new RoleID(1)));
        assertThrows(UnsupportedOperationException.class, () -> entities.channelIDs().add(new ChannelID(1)));
    }

    @Test @Order(20)
    void shouldIsolateGuildExclusions() {
        repository.markExcluded(TestIds.MAIN_GUILD, TestIds.USER_1);
        repository.markExcluded(TestIds.SECOND_GUILD, TestIds.USER_1);

        repository.unmarkExcluded(TestIds.MAIN_GUILD, TestIds.USER_1);

        assertFalse(repository.isExcluded(TestIds.MAIN_GUILD, TestIds.USER_1));
        assertTrue(repository.isExcluded(TestIds.SECOND_GUILD, TestIds.USER_1));
    }

    @Test @Order(21)
    void shouldSeparateEntityTypeExclusions() {
        long id = 7000000000000000000L;
        UserID user = new UserID(id);
        RoleID role = new RoleID(id);
        ChannelID channel = new ChannelID(id);

        repository.markExcluded(TestIds.MAIN_GUILD, user);
        repository.markExcluded(TestIds.MAIN_GUILD, role);
        repository.markExcluded(TestIds.MAIN_GUILD, channel);

        repository.unmarkExcluded(TestIds.MAIN_GUILD, user);

        assertFalse(repository.isExcluded(TestIds.MAIN_GUILD, user));
        assertTrue(repository.isExcluded(TestIds.MAIN_GUILD, role));
        assertTrue(repository.isExcluded(TestIds.MAIN_GUILD, channel));
    }
}
