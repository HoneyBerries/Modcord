package net.honeyberries.action;

import net.dv8tion.jda.api.JDA;
import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.Member;
import net.dv8tion.jda.api.entities.UserSnowflake;
import net.honeyberries.config.AppConfig;
import net.honeyberries.database.repository.GuildModerationActionsRepository;
import net.honeyberries.datatypes.action.ActionData;
import net.honeyberries.discord.JDAManager;
import org.jetbrains.annotations.NotNull;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.Objects;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

/**
 * Handles rollback (reversal) of previously applied moderation actions.
 * Rolls back BAN → unban; TIMEOUT → removes timeout; other action types are logged but not reversed.
 */
public class RollbackHandler {

    /** Singleton instance. */
    @NotNull
    private static final RollbackHandler INSTANCE = new RollbackHandler();
    /** Logger for rollback operations and failures. */
    private final Logger logger = LoggerFactory.getLogger(RollbackHandler.class);
    /** JDA client for Discord API calls. */
    @NotNull
    private final JDA jda = JDAManager.getInstance().getJDA();

    private RollbackHandler() {}

    /**
     * Retrieves the singleton instance of this rollback handler.
     *
     * @return the singleton {@code RollbackHandler}
     */
    public static RollbackHandler getInstance() {
        return INSTANCE;
    }

    /**
     * Reverts a previously applied moderation action.
     * <p>
     * Rolls back BAN → issues unban; TIMEOUT → removes timeout; KICK and WARN have no automated
     * reversal (they are logged only). Records the reversal in {@code guild_moderation_action_reversals}.
     *
     * @param actionId the UUID of the action to revert, must not be {@code null}
     * @param reason   reason for the reversal, displayed in the audit embed, must not be {@code null}
     * @return {@code true} if the reversal was applied or is not applicable; {@code false} on error
     * @throws NullPointerException if {@code actionId} or {@code reason} is {@code null}
     */
    public boolean rollbackAction(@NotNull UUID actionId, @NotNull String reason) {
        Objects.requireNonNull(actionId, "actionId must not be null");
        Objects.requireNonNull(reason, "reason must not be null");

        ActionData action = GuildModerationActionsRepository.getInstance().getActionById(actionId);
        if (action == null) {
            logger.warn("Cannot rollback action {}: not found in database", actionId);
            return false;
        }

        Guild guild = jda.getGuildById(action.guildId().value());
        if (guild == null) {
            logger.warn("Cannot rollback action {}: guild {} not found", actionId, action.guildId());
            return false;
        }

        boolean rolled = switch (action.action()) {
            case BAN -> {
                try {
                    guild.unban(UserSnowflake.fromId(action.userId().value()))
                            .reason("Rollback of action " + actionId + ": " + reason)
                            .timeout(AppConfig.getInstance().getDiscordRequestTimeout(), TimeUnit.SECONDS)
                            .complete();
                    yield true;
                } catch (Exception e) {
                    logger.warn("Failed to unban user {} for rollback of action {}", action.userId(), actionId, e);
                    yield false;
                }
            }
            case TIMEOUT -> {
                try {
                    Member member = guild.retrieveMemberById(action.userId().value())
                            .timeout(AppConfig.getInstance().getDiscordRequestTimeout(), TimeUnit.SECONDS)
                            .complete();
                    if (member == null) {
                        logger.warn("Cannot remove timeout for rollback of action {}: member not found", actionId);
                        yield false;
                    }
                    member.removeTimeout().reason("Rollback of action " + actionId + ": " + reason)
                            .timeout(AppConfig.getInstance().getDiscordRequestTimeout(), TimeUnit.SECONDS)
                            .complete();
                    yield true;
                } catch (Exception e) {
                    logger.warn("Failed to remove timeout for rollback of action {}", actionId, e);
                    yield false;
                }
            }
            // KICK/WARN/DELETE/UNBAN/NULL have no automated reversal
            default -> {
                logger.info("Action {} ({}) has no automated reversal — marking as rolled back", actionId, action.action());
                yield true;
            }
        };

        if (rolled) {
            GuildModerationActionsRepository.getInstance().recordReversal(actionId, reason);
        }

        return rolled;
    }
}
