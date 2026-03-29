package net.honeyberries.datatypes.content;

import net.honeyberries.datatypes.discord.ChannelID;
import org.jetbrains.annotations.NotNull;

/**
 * Metadata about a channel that contributed messages to a server batch.
 */
public record ChannelContext(
        @NotNull ChannelID channelId,
        @NotNull String channelName,
        @NotNull String guidelines,
        int messageCount
) {
    /**
     * Convenience constructor with default guidelinesText and message count.
     */
    public ChannelContext(
            @NotNull ChannelID channelId,
            @NotNull String channelName
    ) {
        this(channelId, channelName, "", 0);
    }
}

