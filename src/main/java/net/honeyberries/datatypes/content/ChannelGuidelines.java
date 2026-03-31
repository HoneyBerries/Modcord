package net.honeyberries.datatypes.content;

import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;

public record ChannelGuidelines
(
        @NotNull GuildID guildId,
        @NotNull ChannelID channelId,
        @Nullable String guidelinesText
) {}
