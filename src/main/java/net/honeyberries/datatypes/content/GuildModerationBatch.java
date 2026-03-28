package net.honeyberries.datatypes.content;

import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import org.jetbrains.annotations.NotNull;

import java.util.List;
import java.util.Map;

/**
 * A batch of messages across all channels in a guild for server-wide AI moderation.
 */
public record GuildModerationBatch(
        @NotNull GuildID guildId,
        @NotNull String guildName,
        @NotNull Map<ChannelID, ChannelContext> channels,
        @NotNull List<ModerationUser> users,
        @NotNull List<ModerationUser> historyUsers
) {
    /**
     * Convenience constructor with empty channels and users.
     */
    public GuildModerationBatch(
            @NotNull GuildID guildId,
            @NotNull String guildName
    ) {
        this(guildId, guildName, Map.of(), List.of(), List.of());
    }

    /**
     * Check if this batch is empty (no users or all users have no channels).
     */
    public boolean isEmpty() {
        return users.isEmpty() || users.stream().allMatch(u -> u.channels().isEmpty());
    }
}

