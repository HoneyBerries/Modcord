package net.honeyberries.datatypes.content;

import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;

public record ChannelGuidelines
(
        GuildID guildId,
        ChannelID channelId,
        String guidelinesText
) {}
