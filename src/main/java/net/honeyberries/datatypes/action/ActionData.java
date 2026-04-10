package net.honeyberries.datatypes.action;

import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.discord.UserID;
import org.jetbrains.annotations.NotNull;

import java.util.List;
import java.util.Objects;
import java.util.UUID;

/**
 * Immutable representation of a moderation action produced by the AI layer.
 * Bundles the action type, optional timing information, and any message deletions so persistence and execution stay in sync.
 * Instances are created either directly from the AI response or reconstructed from the database for scheduled processing.
 */
public record ActionData(
        @NotNull UUID id, // 👈 IMPORTANT (you’ll want this later)
        @NotNull GuildID guildId,
        @NotNull UserID userId,
        @NotNull UserID moderatorId,
        @NotNull ActionType action,
        @NotNull String reason,
        long timeoutDuration,
        long banDuration,
        @NotNull List<MessageDeletion> deletions
) {

    /**
     * Compact constructor enforcing non-null components.
     *
     * @param id               unique identifier for the moderation action
     * @param guildId          guild that the action targets
     * @param userId           user that the action targets
     * @param moderatorId      moderator responsible for the action
     * @param action           moderation action type to execute
     * @param reason           textual reason supplied by the AI
     * @param timeoutDuration  timeout duration in seconds (0 if not applicable)
     * @param banDuration      ban duration in seconds (0 if not applicable)
     * @param deletions        messages scheduled for deletion as part of the action
     * @throws NullPointerException if any non-nullable argument is {@code null}
     */
    public ActionData {
        Objects.requireNonNull(id, "interactionID must not be null");
        Objects.requireNonNull(guildId, "guildId must not be null");
        Objects.requireNonNull(userId, "userId must not be null");
        Objects.requireNonNull(moderatorId, "moderatorId must not be null");
        Objects.requireNonNull(action, "action must not be null");
        Objects.requireNonNull(reason, "reason must not be null");
        Objects.requireNonNull(deletions, "deletions must not be null");
    }

    /**
     * Convenience constructor that defaults the deletions list to empty.
     *
     * @param id              unique identifier for the moderation action
     * @param guildId         guild that the action targets
     * @param userId          user that the action targets
     * @param moderatorId     moderator responsible for the action
     * @param action          moderation action type to execute
     * @param reason          textual reason supplied by the AI
     * @param timeoutDuration timeout duration in seconds (0 if not applicable)
     * @param banDuration     ban duration in seconds (0 if not applicable)
     */
    public ActionData(
            @NotNull UUID id,
            @NotNull GuildID guildId,
            @NotNull UserID userId,
            @NotNull UserID moderatorId,
            @NotNull ActionType action,
            @NotNull String reason,
            long timeoutDuration,
            long banDuration
    ) {
        this(id, guildId, userId, moderatorId, action, reason, timeoutDuration, banDuration, List.of());
    }
}
