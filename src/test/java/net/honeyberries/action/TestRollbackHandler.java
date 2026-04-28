package net.honeyberries.action;

import net.dv8tion.jda.api.JDA;
import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.Member;
import net.honeyberries.config.AppConfig;
import net.honeyberries.database.Database;
import net.honeyberries.database.repository.GuildModerationActionsRepository;
import net.honeyberries.datatypes.action.ActionData;
import net.honeyberries.datatypes.action.ActionType;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.discord.UserID;
import net.honeyberries.discord.JDAManager;
import org.junit.jupiter.api.*;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

@DisplayName("Rollback Handler Tests")
@Tag("integration")
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
public class TestRollbackHandler {

    private static final Database database = Database.getInstance();
    private static final AppConfig appConfig = AppConfig.getInstance();

    private static final long TEST_ACCOUNT_2_ID = 1180022370375835731L;
    private static final long TEST_GUILD_ID = 1488762869880324200L;

    private final ActionHandler actionHandler = ActionHandler.getInstance();
    private final RollbackHandler rollbackHandler = RollbackHandler.getInstance();
    private final GuildModerationActionsRepository actionRepository = GuildModerationActionsRepository.getInstance();

    @BeforeAll
    static void setup() {
        database.initialize(appConfig);
    }

    @Test
    @DisplayName("should apply timeout and rollback after 5 seconds")
    @Order(1)
    void shouldTimeoutThenRollback() {
        Guild guild = getGuildOrSkip();
        ensureMemberPresent(guild, TEST_ACCOUNT_2_ID);
        clearTimeoutIfPresent(guild, TEST_ACCOUNT_2_ID);

        // Apply timeout
        long timeoutSeconds = 120;
        ActionData timeoutAction = new ActionData(
                UUID.randomUUID(),
                Instant.now(),
                new GuildID(TEST_GUILD_ID),
                new UserID(TEST_ACCOUNT_2_ID),
                new UserID(TEST_ACCOUNT_2_ID),
                ActionType.TIMEOUT,
                "Test timeout for rollback",
                timeoutSeconds,
                0,
                List.of()
        );

        UUID testTimeoutActionId = timeoutAction.id();

        // Save action to database first
        boolean saved = actionRepository.addActionToDatabase(timeoutAction);
        Assertions.assertTrue(saved, "Action should be saved to database");

        boolean applied = actionHandler.processAction(timeoutAction);
        Assertions.assertTrue(applied, "TIMEOUT action should apply successfully");

        // Verify timeout was applied
        Member timedOutMember = guild.retrieveMemberById(TEST_ACCOUNT_2_ID).complete();
        Assertions.assertNotNull(timedOutMember, "Member should be retrievable");
        Assertions.assertTrue(timedOutMember.isTimedOut(), "Member should be timed out after action application");

        // Wait 5 seconds
        try {
            Thread.sleep(5000);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            Assertions.fail("Thread sleep interrupted during test");
        }

        // Rollback timeout
        boolean rolledBack = rollbackHandler.rollbackAction(testTimeoutActionId, "Test rollback after 5 seconds");
        Assertions.assertTrue(rolledBack, "Timeout should be rolled back successfully");

        // Verify timeout was removed
        Member refreshedMember = guild.retrieveMemberById(TEST_ACCOUNT_2_ID).complete();
        Assertions.assertNotNull(refreshedMember, "Member should still be retrievable after rollback");
        Assertions.assertFalse(refreshedMember.isTimedOut(), "Member should no longer be timed out after rollback");
    }

    private Guild getGuildOrSkip() {
        JDA jda = JDAManager.getInstance().getJDA();
        Guild guild = jda.getGuildById(TEST_GUILD_ID);
        Assumptions.assumeTrue(guild != null, "Test guild not found. Ensure bot is in the guild and ID is correct.");
        return guild;
    }

    private Member ensureMemberPresent(Guild guild, long userId) {
        Member member = guild.retrieveMemberById(userId).complete();
        Assumptions.assumeTrue(member != null, "Member " + userId + " not found in test guild.");
        return member;
    }

    private void clearTimeoutIfPresent(Guild guild, long userId) {
        try {
            Member member = guild.retrieveMemberById(userId).complete();
            if (member != null && member.isTimedOut()) {
                member.removeTimeout().reason("Clearing timeout before integration test").complete();
            }
        } catch (Exception ignored) {
            // Best-effort cleanup: do not fail tests from teardown noise.
        }
    }
}
