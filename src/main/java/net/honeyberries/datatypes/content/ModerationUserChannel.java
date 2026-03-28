package net.honeyberries.datatypes.content;

import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.UserID;
import org.jetbrains.annotations.NotNull;

import java.util.List;

/**
 * A single channel's messages belonging to one user.
 */
public record ModerationUserChannel(
        @NotNull UserID userId,
        @NotNull ChannelID channelId,
        @NotNull String channelName,
        @NotNull List<ModerationMessage> messages
) {
}

