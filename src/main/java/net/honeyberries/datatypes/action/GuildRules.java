package net.honeyberries.datatypes.action;

import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;

/**
 * Represents a guild rule stored in the database.
 * <p>
 * Contains guild ID, channel ID where rules are displayed, and the rule text content.
 * Also tracks creation and update timestamps.
 */
public record GuildRules(
        GuildID guildId,
        String rulesText
) { }