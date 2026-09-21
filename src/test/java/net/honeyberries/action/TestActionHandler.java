package net.honeyberries.action;

import net.dv8tion.jda.api.JDA;
import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.Member;
import net.dv8tion.jda.api.entities.Message;
import net.dv8tion.jda.api.entities.channel.Channel;
import net.dv8tion.jda.api.entities.channel.middleman.MessageChannel;
import net.honeyberries.ResourceInitializer;
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

@DisplayName("Action Handler Tests")
@Tag("integration")
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
public class TestActionHandler extends PostgresTestSupport {

    static {
        ResourceInitializer.initialize();
    }

    private static final long TEST_ACCOUNT_1_ID = 1104649796821729320L;
    private static final long TEST_ACCOUNT_2_ID = 1180022370375835731L;
    private static final long TEST_ACCOUNT_3_ID = 1260476582519242767L;

    private static final long TEST_GUILD_ID = 1488762869880324200L;
    private static final long TEST_CHANNEL_OUTPUT_ID = 1489002480477143265L;

    private final ActionHandler actionHandler = ActionHandler.getInstance();

    @BeforeAll
    void seedGuildPreferences() {
        GuildPreferences prefs = GuildPreferences.defaults(new GuildID(TEST_GUILD_ID))
                .withAuditLogChannelId(new ChannelID(TEST_CHANNEL_OUTPUT_ID));
        boolean saved = PreferencesManager.getInstance().updatePreferences(prefs);
        Assertions.assertTrue(saved, "Guild preferences (audit channel) should be seeded successfully");
    }

    @Test
    @DisplayName("test account 1 should be warned")
    void shouldWarnTestAccount1() {
        Guild guild = getGuildOrSkip();
        ensureMemberPresent(guild, TEST_ACCOUNT_1_ID);
        MessageChannel outputChannel = ensureOutputChannelPresent(guild);

        ActionData actionData = createAction(TEST_ACCOUNT_1_ID, ActionType.WARN, 0, 0);

        boolean applied = actionHandler.processAction(actionData);
        Assertions.assertTrue(applied, "WARN action should apply successfully for test account 1");

        assertAuditEmbedPosted(outputChannel, actionData.id());
    }

    @Test
    @DisplayName("test account 2 should be timed out for 2 minutes")
    void shouldTimeoutTestAccount2() {
        Guild guild = getGuildOrSkip();
        ensureMemberPresent(guild, TEST_ACCOUNT_2_ID);
        MessageChannel outputChannel = ensureOutputChannelPresent(guild);

        clearTimeoutIfPresent(guild, TEST_ACCOUNT_2_ID);

        ActionData actionData = createAction(TEST_ACCOUNT_2_ID, ActionType.TIMEOUT, 120, 0);

        boolean applied = actionHandler.processAction(actionData);
        Assertions.assertTrue(applied, "TIMEOUT action should apply successfully for test account 2");

        Member refreshed = guild.retrieveMemberById(TEST_ACCOUNT_2_ID).complete();
        Assertions.assertNotNull(refreshed, "Timed out member should still be retrievable");
        Assertions.assertTrue(refreshed.isTimedOut(), "test account 2 should be timed out after action application");

        assertAuditEmbedPosted(outputChannel, actionData.id());
    }

    @Test
    @DisplayName("test account 3 should be timed out for 5 minutes")
    void shouldTimeoutTestAccount3() {
        Guild guild = getGuildOrSkip();
        ensureMemberPresent(guild, TEST_ACCOUNT_3_ID);
        MessageChannel outputChannel = ensureOutputChannelPresent(guild);

        clearTimeoutIfPresent(guild, TEST_ACCOUNT_3_ID);

        ActionData actionData = createAction(TEST_ACCOUNT_3_ID, ActionType.TIMEOUT, 300, 0);

        boolean applied = actionHandler.processAction(actionData);
        Assertions.assertTrue(applied, "TIMEOUT action should apply successfully for test account 3");

        Member refreshed = guild.retrieveMemberById(TEST_ACCOUNT_3_ID).complete();
        Assertions.assertNotNull(refreshed, "Timed out member should still be retrievable");
        Assertions.assertTrue(refreshed.isTimedOut(), "test account 3 should be timed out after action application");

        assertAuditEmbedPosted(outputChannel, actionData.id());
    }

    private ActionData createAction(long userId, ActionType actionType, long timeoutDuration, long banDuration) {
        return new ActionData(
                UUID.randomUUID(),
                Instant.now(),
                new GuildID(TEST_GUILD_ID),
                new UserID(userId),
                new UserID(TEST_ACCOUNT_1_ID),
                actionType,
                "Integration test action from TestActionHandler",
                timeoutDuration,
                banDuration,
                List.of()
        );
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

    private void clearTimeoutIfPresent(Guild guild, long userId) {
        try {
            Member member = guild.retrieveMemberById(userId).complete();
            if (member != null && member.isTimedOut()) {
                member.removeTimeout().reason("Clearing timeout after integration test").complete();
            }
        } catch (Exception ignored) {
            // Best-effort cleanup: do not fail tests from teardown noise.
        }
    }
}
