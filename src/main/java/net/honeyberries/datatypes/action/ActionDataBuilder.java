package net.honeyberries.datatypes.action;

import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.discord.UserID;
import org.jetbrains.annotations.NotNull;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

/**
 * Mutable helper for assembling {@link ActionData} instances from disparate pieces of AI output.
 * Allows incremental construction of the action definition and associated deletions before producing an immutable record.
 */
public class ActionDataBuilder {
    private final @NotNull UUID id;
    private final @NotNull GuildID guildId;
    private final @NotNull UserID userId;
    private final @NotNull UserID moderatorId;
    private final @NotNull ActionType action;
    private final @NotNull String reason;
    private final long timeoutDuration;
    private final long banDuration;
    private final @NotNull List<MessageDeletion> messageDeletions = new ArrayList<>();

    /**
     * Creates a builder with the core moderation decision payload.
     *
     * @param id              unique identifier for the moderation action; must not be {@code null}
     * @param guildId         guild being moderated; must not be {@code null}
     * @param userId          user receiving the action; must not be {@code null}
     * @param moderatorId     moderator performing the action; must not be {@code null}
     * @param action          action to perform; must not be {@code null}
     * @param reason          textual reason returned by the AI; must not be {@code null}
     * @param timeoutDuration timeout duration in seconds (0 if not used)
     * @param banDuration     ban duration in seconds (0 if not used)
     * @throws NullPointerException if any required argument is {@code null}
     */
    public ActionDataBuilder(
            @NotNull UUID id,
            @NotNull GuildID guildId,
            @NotNull UserID userId,
            @NotNull UserID moderatorId,
            @NotNull ActionType action,
            @NotNull String reason,
            long timeoutDuration,
            long banDuration
    ) {
        this.id = Objects.requireNonNull(id, "interactionID must not be null");
        this.guildId = Objects.requireNonNull(guildId, "guildId must not be null");
        this.userId = Objects.requireNonNull(userId, "userId must not be null");
        this.moderatorId = Objects.requireNonNull(moderatorId, "moderatorId must not be null");
        this.action = Objects.requireNonNull(action, "action must not be null");
        this.reason = Objects.requireNonNull(reason, "reason must not be null");
        this.timeoutDuration = timeoutDuration;
        this.banDuration = banDuration;
    }

    /**
     * Adds a message deletion to be applied alongside the moderation action.
     *
     * @param deletion message deletion specification; must not be {@code null}
     * @throws NullPointerException if {@code deletion} is {@code null}
     */
    public void addMessageDeletion(@NotNull MessageDeletion deletion) {
        messageDeletions.add(Objects.requireNonNull(deletion, "deletion must not be null"));
    }

    /**
     * Produces an immutable {@link ActionData} snapshot of the current builder state.
     *
     * @return immutable moderation action definition
     */
    @NotNull
    public ActionData build() {
        return new ActionData(
                id,
                guildId,
                userId,
                moderatorId,
                action,
                reason,
                timeoutDuration,
                banDuration,
                messageDeletions
        );
    }
}
