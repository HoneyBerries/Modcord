package net.honeyberries.datatypes.action;

import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.MessageID;
import org.jetbrains.annotations.NotNull;

import java.util.List;
import java.util.Objects;

/**
 * Aggregates a channel identifier with the set of message snowflakes scheduled for deletion.
 * Keeps the per-channel grouping explicit so higher-level orchestrators can batch deletion calls efficiently.
 */
public record ChannelDeleteSpec(
        @NotNull ChannelID channelId,
        @NotNull List<MessageID> messageIds
) {
    /**
     * Ensures the channel and message collection references are never {@code null}.
     *
     * @param channelId  target channel whose messages should be removed; must not be {@code null}
     * @param messageIds identifiers of messages to delete (may be empty but never {@code null})
     * @throws NullPointerException if any non-nullable argument is {@code null}
     */
    public ChannelDeleteSpec {
        Objects.requireNonNull(channelId, "channelId must not be null");
        Objects.requireNonNull(messageIds, "messageIds must not be null");
    }

    /**
     * Convenience constructor that initializes with an empty message interactionID list.
     *
     * @param channelId target channel whose messages should be removed; must not be {@code null}
     * @throws NullPointerException if {@code channelId} is {@code null}
     */
    public ChannelDeleteSpec(@NotNull ChannelID channelId) {
        this(channelId, List.of());
    }
}
