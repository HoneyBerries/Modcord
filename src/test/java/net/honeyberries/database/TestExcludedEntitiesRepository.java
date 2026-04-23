package net.honeyberries.database;

import net.honeyberries.config.AppConfig;
import net.honeyberries.database.repository.ExcludedEntitiesRepository;
import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.discord.RoleID;
import net.honeyberries.datatypes.discord.UserID;
import org.junit.jupiter.api.*;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

@DisplayName("Excluded Entities Repository Tests")
@Tag("integration")
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
public class TestExcludedEntitiesRepository {

    private static final Database database = Database.getInstance();
    private static final AppConfig appConfig = AppConfig.getInstance();
    private static final ExcludedEntitiesRepository repository = ExcludedEntitiesRepository.getInstance();

    /**
     * =========================
     * Centralized Test IDs
     * =========================
     */
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

    @BeforeAll
    static void setup() {
        database.initialize(appConfig);
    }

    // ─────────────── USERS ───────────────

    @Test @Order(1)
    void shouldMarkUser() {
        assertTrue(repository.markExcluded(TestIds.MAIN_GUILD, TestIds.USER_1));
    }

    @Test @Order(2)
    void shouldVerifyUserExcluded() {
        assertTrue(repository.isExcluded(TestIds.MAIN_GUILD, TestIds.USER_1));
    }

    @Test @Order(3)
    void shouldVerifyUserNotExcluded() {
        assertFalse(repository.isExcluded(TestIds.MAIN_GUILD, TestIds.USER_3));
    }

    @Test @Order(4)
    void shouldMarkMultipleUsers() {
        repository.markExcluded(TestIds.MAIN_GUILD, TestIds.USER_2);
        repository.markExcluded(TestIds.MAIN_GUILD, TestIds.USER_3);

        assertTrue(repository.isExcluded(TestIds.MAIN_GUILD, TestIds.USER_2));
        assertTrue(repository.isExcluded(TestIds.MAIN_GUILD, TestIds.USER_3));
    }

    @Test @Order(5)
    void shouldBeIdempotentUserMark() {
        repository.markExcluded(TestIds.MAIN_GUILD, TestIds.USER_1);
        assertTrue(repository.markExcluded(TestIds.MAIN_GUILD, TestIds.USER_1));
    }

    @Test @Order(6)
    void shouldUnmarkUser() {
        repository.unmarkExcluded(TestIds.MAIN_GUILD, TestIds.USER_1);
        assertFalse(repository.isExcluded(TestIds.MAIN_GUILD, TestIds.USER_1));
    }

    // ─────────────── ROLES ───────────────

    @Test @Order(10)
    void shouldMarkRole() {
        assertTrue(repository.markExcluded(TestIds.MAIN_GUILD, TestIds.ROLE_1));
    }

    @Test @Order(11)
    void shouldVerifyRoleExcluded() {
        assertTrue(repository.isExcluded(TestIds.MAIN_GUILD, TestIds.ROLE_1));
    }

    @Test @Order(12)
    void shouldVerifyRoleNotExcluded() {
        assertFalse(repository.isExcluded(TestIds.MAIN_GUILD, TestIds.ROLE_3));
    }

    @Test @Order(13)
    void shouldMarkMultipleRoles() {
        repository.markExcluded(TestIds.MAIN_GUILD, TestIds.ROLE_2);
        repository.markExcluded(TestIds.MAIN_GUILD, TestIds.ROLE_3);

        assertTrue(repository.isExcluded(TestIds.MAIN_GUILD, TestIds.ROLE_2));
        assertTrue(repository.isExcluded(TestIds.MAIN_GUILD, TestIds.ROLE_3));
    }

    // ─────────────── CHANNELS ───────────────

    @Test @Order(20)
    void shouldMarkChannel() {
        assertTrue(repository.markExcluded(TestIds.MAIN_GUILD, TestIds.CHANNEL_1));
    }

    @Test @Order(21)
    void shouldVerifyChannelExcluded() {
        assertTrue(repository.isExcluded(TestIds.MAIN_GUILD, TestIds.CHANNEL_1));
    }

    @Test @Order(22)
    void shouldVerifyChannelNotExcluded() {
        assertFalse(repository.isExcluded(TestIds.MAIN_GUILD, TestIds.CHANNEL_3));
    }

    // ─────────────── GET ALL ───────────────

    @Test @Order(30)
    void shouldReturnEmptyForNewGuild() {
        var entities = repository.getExcludedEntities(TestIds.EMPTY_GUILD);
        assertTrue(entities.userIDs().isEmpty());
        assertTrue(entities.roleIDs().isEmpty());
        assertTrue(entities.channelIDs().isEmpty());
    }

    @Test @Order(31)
    void shouldReturnUsers() {
        repository.markExcluded(TestIds.MAIN_GUILD, TestIds.USER_1);
        repository.markExcluded(TestIds.MAIN_GUILD, TestIds.USER_2);

        var entities = repository.getExcludedEntities(TestIds.MAIN_GUILD);
        assertTrue(entities.userIDs().contains(TestIds.USER_1));
        assertTrue(entities.userIDs().contains(TestIds.USER_2));
    }

    @Test @Order(32)
    void shouldReturnRoles() {
        repository.markExcluded(TestIds.MAIN_GUILD, TestIds.ROLE_1);
        var entities = repository.getExcludedEntities(TestIds.MAIN_GUILD);
        assertTrue(entities.roleIDs().contains(TestIds.ROLE_1));
    }

    @Test @Order(33)
    void shouldReturnChannels() {
        repository.markExcluded(TestIds.MAIN_GUILD, TestIds.CHANNEL_1);
        var entities = repository.getExcludedEntities(TestIds.MAIN_GUILD);
        assertTrue(entities.channelIDs().contains(TestIds.CHANNEL_1));
    }

    @Test @Order(34)
    void shouldBeImmutable() {
        var entities = repository.getExcludedEntities(TestIds.MAIN_GUILD);

        assertThrows(UnsupportedOperationException.class, () -> entities.userIDs().add(new UserID(1)));
        assertThrows(UnsupportedOperationException.class, () -> entities.roleIDs().add(new RoleID(1)));
        assertThrows(UnsupportedOperationException.class, () -> entities.channelIDs().add(new ChannelID(1)));
    }

    // ─────────────── ISOLATION ───────────────

    @Test @Order(40)
    void shouldIsolateGuilds() {
        repository.markExcluded(TestIds.MAIN_GUILD, TestIds.USER_1);
        repository.markExcluded(TestIds.SECOND_GUILD, TestIds.USER_1);

        repository.unmarkExcluded(TestIds.MAIN_GUILD, TestIds.USER_1);

        assertFalse(repository.isExcluded(TestIds.MAIN_GUILD, TestIds.USER_1));
        assertTrue(repository.isExcluded(TestIds.SECOND_GUILD, TestIds.USER_1));
    }

    @Test @Order(41)
    void shouldSeparateEntityTypes() {
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

    @Test @Order(42)
    void shouldContainAllUsers() {
        repository.markExcluded(TestIds.MAIN_GUILD, TestIds.USER_1);
        repository.markExcluded(TestIds.MAIN_GUILD, TestIds.USER_2);
        repository.markExcluded(TestIds.MAIN_GUILD, TestIds.USER_3);

        List<UserID> users = repository.getExcludedEntities(TestIds.MAIN_GUILD).userIDs();

        assertTrue(users.contains(TestIds.USER_1));
        assertTrue(users.contains(TestIds.USER_2));
        assertTrue(users.contains(TestIds.USER_3));
    }
}
