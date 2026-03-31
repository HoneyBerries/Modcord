package net.honeyberries.datatypes.content;

import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.UserID;
import org.jetbrains.annotations.NotNull;

import java.util.List;
import java.util.Objects;

/**
 * Bundles a user's messages within a specific channel along with a human-readable channel name.
 * Used to provide fine-grained context to the AI so actions can be traced back to where conversations happened.
 */
public record ModerationUserChannel(
        @NotNull UserID userId,
        @NotNull ChannelID channelId,
        @NotNull String channelName,
        @NotNull List<ModerationMessage> messages
) {
    /**
     * Validates required references for the per-channel grouping.
     *
     * @param userId      user that authored the messages; must not be {@code null}
     * @param channelId   channel containing the messages; must not be {@code null}
     * @param channelName display name for the channel; must not be {@code null}
     * @param messages    messages authored by the user in this channel; may be empty but not {@code null}
     * @throws NullPointerException if any required argument is {@code null}
     */
    public ModerationUserChannel {
        Objects.requireNonNull(userId, "userId must not be null");
        Objects.requireNonNull(channelId, "channelId must not be null");
        Objects.requireNonNull(channelName, "channelName must not be null");
        Objects.requireNonNull(messages, "messages must not be null");
    }
}
