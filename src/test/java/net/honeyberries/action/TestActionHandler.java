package net.honeyberries.action;

import net.dv8tion.jda.api.JDA;
import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.Member;
import net.dv8tion.jda.api.entities.channel.Channel;
import net.honeyberries.config.AppConfig;
import net.honeyberries.database.Database;
import net.honeyberries.datatypes.action.ActionData;
import net.honeyberries.datatypes.action.ActionType;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.discord.UserID;
import net.honeyberries.discord.JDAManager;
import org.junit.jupiter.api.*;

import java.util.EnumMap;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ThreadLocalRandom;

@DisplayName("Action Handler Tests")
@Tag("integration")
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
public class TestActionHandler {

    private static final Database database = Database.getInstance();
    private static final AppConfig appConfig = AppConfig.getInstance();

    private static final long TEST_ACCOUNT_1_ID = 1104649796821729320L;
    private static final long TEST_ACCOUNT_2_ID = 1180022370375835731L;
    private static final long TEST_ACCOUNT_3_ID = 1260476582519242767L;

    private static final long TEST_GUILD_ID = 1488762869880324200L;
    private static final long TEST_CHANNEL_OUTPUT_ID = 1489002480477143265L;

    private final ActionHandler actionHandler = ActionHandler.getInstance();


    @BeforeAll
    static void setup() {
        database.initialize(appConfig);
    }

    @Test
    @DisplayName("test account 1 should be warned")
    void shouldWarnTestAccount1() {
        Guild guild = getGuildOrSkip();
        ensureMemberPresent(guild, TEST_ACCOUNT_1_ID);
        ensureOutputChannelPresent(guild);

        ActionData actionData = createAction(TEST_ACCOUNT_1_ID, ActionType.WARN, 0, 0);

        boolean applied = actionHandler.processAction(actionData);
        Assertions.assertTrue(applied, "WARN action should apply successfully for test account 1");
    }

    @Test
    @DisplayName("test account 2 should be timeouted")
    void shouldTimeoutTestAccount2() {
        Guild guild = getGuildOrSkip();
        Member member = ensureMemberPresent(guild, TEST_ACCOUNT_2_ID);
        ensureOutputChannelPresent(guild);

        clearTimeoutIfPresent(guild, TEST_ACCOUNT_2_ID);

        long timeoutSeconds = 120;
        ActionData actionData = createAction(TEST_ACCOUNT_2_ID, ActionType.TIMEOUT, timeoutSeconds, 0);

        boolean applied = actionHandler.processAction(actionData);
        Assertions.assertTrue(applied, "TIMEOUT action should apply successfully for test account 2");

        Member refreshed = guild.retrieveMemberById(TEST_ACCOUNT_2_ID).complete();
        Assertions.assertNotNull(refreshed, "Timed out member should still be retrievable");
        Assertions.assertTrue(refreshed.isTimedOut(), "test account 2 should be timed out after action application");
    }

    @Test
    @DisplayName("test account 3 action should be warn/timeout/null with 1/3 random selection")
    void testAccount3RandomSelectionAndExecution() {
        Guild guild = getGuildOrSkip();
        ensureMemberPresent(guild, TEST_ACCOUNT_3_ID);
        ensureOutputChannelPresent(guild);

        Map<ActionType, Integer> counts = new EnumMap<>(ActionType.class);
        counts.put(ActionType.WARN, 0);
        counts.put(ActionType.TIMEOUT, 0);
        counts.put(ActionType.NULL, 0);

        int trials = 900;
        ActionType lastPicked = ActionType.NULL; // <-- track the last pick inside the loop
        for (int i = 0; i < trials; i++) {
            lastPicked = pickRandomActionForAccount3();
            counts.computeIfPresent(lastPicked, (k, v) -> v + 1);
        }

        double warnRatio = counts.get(ActionType.WARN) / (double) trials;
        double timeoutRatio = counts.get(ActionType.TIMEOUT) / (double) trials;
        double nullRatio = counts.get(ActionType.NULL) / (double) trials;

        Assertions.assertTrue(warnRatio > 0.25 && warnRatio < 0.42,
                "WARN ratio should be near 1/3; actual=" + warnRatio);
        Assertions.assertTrue(timeoutRatio > 0.25 && timeoutRatio < 0.42,
                "TIMEOUT ratio should be near 1/3; actual=" + timeoutRatio);
        Assertions.assertTrue(nullRatio > 0.25 && nullRatio < 0.42,
                "NULL ratio should be near 1/3; actual=" + nullRatio);

        // Re-use lastPicked instead of calling pickRandomActionForAccount3() again,
        // which was generating a second independent action and causing double-application.
        long timeoutSeconds = lastPicked == ActionType.TIMEOUT ? 120 : 0;
        ActionData actionData = createAction(TEST_ACCOUNT_3_ID, lastPicked, timeoutSeconds, 0);

        boolean applied = actionHandler.processAction(actionData);
        Assertions.assertTrue(applied,
                "Random action should apply successfully for test account 3 when picked action is " + lastPicked);
    }

    private ActionData createAction(long userId, ActionType actionType, long timeoutDuration, long banDuration) {
        return new ActionData(
                UUID.randomUUID(),
                new GuildID(TEST_GUILD_ID),
                new UserID(userId),
                new UserID(TEST_ACCOUNT_1_ID),
                actionType,
                "Integration test action from TestActionHandler",
                timeoutDuration,
                banDuration
        );
    }

    private ActionType pickRandomActionForAccount3() {
        int pick = ThreadLocalRandom.current().nextInt(3);
        return switch (pick) {
            case 0 -> ActionType.WARN;
            case 1 -> ActionType.TIMEOUT;
            default -> ActionType.NULL;
        };
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

    private void ensureOutputChannelPresent(Guild guild) {
        Channel channel = guild.getGuildChannelById(TEST_CHANNEL_OUTPUT_ID);
        Assumptions.assumeTrue(channel != null,
                "Output channel not found in test guild. Check testChannelOutputID.");
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
