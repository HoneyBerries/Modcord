package net.honeyberries.database;

import net.honeyberries.database.repository.SpecialUsersRepository;
import net.honeyberries.datatypes.discord.DiscordUser;
import net.honeyberries.datatypes.discord.UserID;
import net.honeyberries.support.PostgresTestSupport;
import org.junit.jupiter.api.*;

import static org.junit.jupiter.api.Assertions.*;

@DisplayName("Special Users Repo Tests")
@Tag("integration")
public class TestSpecialUsersRepo extends PostgresTestSupport {

    private final SpecialUsersRepository repository = SpecialUsersRepository.getInstance();

    private static final UserID TEST_USER_ID = new UserID(123456789L);
    private static final DiscordUser TEST_USER = new DiscordUser(TEST_USER_ID, "testuser");

    @AfterEach
    void cleanup() {
        repository.removeSpecialUser(TEST_USER_ID);
    }

    @Test
    @DisplayName("Should add and check special user")
    void shouldAddAndCheck() {
        assertTrue(repository.addOrUpdateSpecialUser(TEST_USER));
        assertTrue(repository.isSpecialUser(TEST_USER_ID));
        
        repository.removeSpecialUser(TEST_USER_ID);
        assertFalse(repository.isSpecialUser(TEST_USER_ID));
    }

    @Test
    @DisplayName("Should update special user username")
    void shouldUpdateUsername() {
        repository.addOrUpdateSpecialUser(TEST_USER);
        
        DiscordUser updatedUser = new DiscordUser(TEST_USER_ID, "newname");
        assertTrue(repository.addOrUpdateSpecialUser(updatedUser));
        
        assertTrue(repository.isSpecialUser(TEST_USER_ID));
    }
}
