package net.honeyberries.datatypes.content;

import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;

import java.util.Objects;

/**
 * Captures the current guidelines text configured for a specific guild channel.
 * The guidelines text may be {@code null} when not yet fetched or defined, but the owning guild and channel identifiers are always present.
 */
public record ChannelGuidelines
(
        @NotNull GuildID guildId,
        @NotNull ChannelID channelId,
        @Nullable String guidelinesText
) {
    /**
     * Compact constructor guarding mandatory identifiers.
     *
     * @param guildId        guild that owns the channel; must not be {@code null}
     * @param channelId      channel whose guidelines are tracked; must not be {@code null}
     * @param guidelinesText nullable human-readable guidelines for the channel
     * @throws NullPointerException if {@code guildId} or {@code channelId} is {@code null}
     */
    public ChannelGuidelines {
        Objects.requireNonNull(guildId, "guildId must not be null");
        Objects.requireNonNull(channelId, "channelId must not be null");
    }
}
