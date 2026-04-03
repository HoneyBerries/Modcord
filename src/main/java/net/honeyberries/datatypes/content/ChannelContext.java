package net.honeyberries.datatypes.content;

import net.honeyberries.datatypes.discord.ChannelID;
import org.jetbrains.annotations.NotNull;

import java.util.Objects;

/**
 * Describes a guild channel contributing to a moderation batch, including guidelines text and message volume.
 * Keeps the AI aware of channel context so responses can reflect channel-specific policies.
 */
public record ChannelContext(
        @NotNull ChannelID channelId,
        @NotNull String channelName,
        @NotNull String guidelines,
        int messageCount
) {
    /**
     * Validates channel metadata inputs.
     *
     * @param channelId    channel identifier; must not be {@code null}
     * @param channelName  human-readable name; must not be {@code null}
     * @param guidelines   channel guidelines text (empty if none); must not be {@code null}
     * @param messageCount number of messages contributing to the batch
     * @throws NullPointerException if any required argument is {@code null}
     */
    public ChannelContext {
        Objects.requireNonNull(channelId, "channelId must not be null");
        Objects.requireNonNull(channelName, "channelName must not be null");
        Objects.requireNonNull(guidelines, "guidelines must not be null");
    }

}
