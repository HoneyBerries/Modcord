package net.honeyberries.action;

import net.dv8tion.jda.api.JDA;
import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.Member;
import net.dv8tion.jda.api.entities.Message;
import net.dv8tion.jda.api.entities.channel.Channel;
import net.dv8tion.jda.api.entities.channel.middleman.MessageChannel;
import net.honeyberries.ResourceInitializer;
import net.honeyberries.database.repository.GuildModerationActionsRepository;
import net.honeyberries.datatypes.action.ActionData;
import net.honeyberries.datatypes.action.ActionType;
import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.discord.UserID;
import net.honeyberries.datatypes.preferences.GuildPreferences;
import net.honeyberries.discord.JDAManager;
import net.honeyberries.preferences.PreferencesManager;
import net.honeyberries.support.PostgresTestSupport;
import org.junit.jupiter.api.*;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

@DisplayName("Rollback Handler Tests")
@Tag("integration")
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
public class TestRollbackHandler extends PostgresTestSupport {

    static {
        ResourceInitializer.initialize();
    }

    private static final long TEST_ACCOUNT_2_ID = 1180022370375835731L;
    private static final long TEST_GUILD_ID = 1488762869880324200L;
    private static final long TEST_CHANNEL_OUTPUT_ID = 1489002480477143265L;

    private final ActionHandler actionHandler = ActionHandler.getInstance();
    private final RollbackHandler rollbackHandler = RollbackHandler.getInstance();
    private final GuildModerationActionsRepository actionRepository = GuildModerationActionsRepository.getInstance();

    @BeforeAll
    void seedGuildPreferences() {
        GuildPreferences prefs = GuildPreferences.defaults(new GuildID(TEST_GUILD_ID))
                .withAuditLogChannelId(new ChannelID(TEST_CHANNEL_OUTPUT_ID));
        boolean saved = PreferencesManager.getInstance().updatePreferences(prefs);
        Assertions.assertTrue(saved, "Guild preferences (audit channel) should be seeded successfully");
    }

    @Test
    @DisplayName("should apply timeout and rollback after 5 seconds")
    @Order(1)
    void shouldTimeoutThenRollback() {
        Guild guild = getGuildOrSkip();
        ensureMemberPresent(guild, TEST_ACCOUNT_2_ID);
        MessageChannel outputChannel = ensureOutputChannelPresent(guild);
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

        assertAuditEmbedPosted(outputChannel, testTimeoutActionId);

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

    private void ensureMemberPresent(Guild guild, long userId) {
        Member member = guild.retrieveMemberById(userId).complete();
        Assumptions.assumeTrue(member != null, "Member " + userId + " not found in test guild.");
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

    private MessageChannel ensureOutputChannelPresent(Guild guild) {
        Channel channel = guild.getGuildChannelById(TEST_CHANNEL_OUTPUT_ID);
        Assumptions.assumeTrue(channel != null,
                "Output channel not found in test guild. Check testChannelOutputID.");
        Assumptions.assumeTrue(channel instanceof MessageChannel,
                "Output channel is not message-capable. Check testChannelOutputID.");
        return (MessageChannel) channel;
    }

    /**
     * Polls the output channel's recent history for an embed whose footer references the
     * given action ID, since {@code NotificationService.postToAuditChannel} sends asynchronously.
     */
    private void assertAuditEmbedPosted(MessageChannel channel, UUID actionId) {
        long deadline = System.currentTimeMillis() + 10_000;
        while (System.currentTimeMillis() < deadline) {
            List<Message> recent = channel.getHistory().retrievePast(10).complete();
            boolean found = recent.stream()
                    .flatMap(m -> m.getEmbeds().stream())
                    .anyMatch(e -> e.getFooter() != null && e.getFooter().getText() != null
                            && e.getFooter().getText().contains(actionId.toString()));
            if (found) return;
            try {
                Thread.sleep(500);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                Assertions.fail("Interrupted while waiting for audit log embed for action " + actionId);
            }
        }
        Assertions.fail("Audit log embed for action " + actionId + " was not found in output channel within timeout");
    }
}
