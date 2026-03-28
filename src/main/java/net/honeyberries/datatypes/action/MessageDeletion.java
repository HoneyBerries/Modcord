package net.honeyberries.datatypes.action;

import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.MessageID;

public record MessageDeletion(
    ChannelID channelId,
    MessageID messageId
) {}
