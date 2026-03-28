package net.honeyberries.datatypes.action;

import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.MessageID;

import java.util.List;

/**
 * Messages to delete from a specific channel.
 */
public record ChannelDeleteSpec(
        ChannelID channelId,
        List<MessageID> messageIds
) {
    /**
     * Convenience constructor with empty message IDs list.
     */
    public ChannelDeleteSpec(ChannelID channelId) {
        this(channelId, List.of());
    }
}

