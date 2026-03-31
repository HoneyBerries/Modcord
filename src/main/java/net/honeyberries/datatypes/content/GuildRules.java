package net.honeyberries.datatypes.content;

import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;

/**
 * Represents a guild rule stored in the database.
 * <p>
 * Contains guild ID, channel ID where rules are displayed, and the rule text content.
 * Also tracks creation and update timestamps.
 */
public record GuildRules(
        @NotNull GuildID guildId,
        @Nullable ChannelID rulesChannelId,
        @Nullable String rulesText
) { }