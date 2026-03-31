package net.honeyberries.datatypes.content;

import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;

import java.util.Objects;

/**
 * Snapshot of a guild's rules text and the channel used to publish it.
 * Provides a single container that can be persisted or refreshed from Discord without losing the owning guild reference.
 * The channel id and text may be absent when rules are not configured or have been cleared.
 */
public record GuildRules(
        @NotNull GuildID guildId,
        @Nullable ChannelID rulesChannelId,
        @Nullable String rulesText
) {
    /**
     * Compact constructor validating the owning guild reference.
     *
     * @param guildId        guild that owns the rules; must not be {@code null}
     * @param rulesChannelId optional channel that displays the rules
     * @param rulesText      optional rules text content
     * @throws NullPointerException if {@code guildId} is {@code null}
     */
    public GuildRules {
        Objects.requireNonNull(guildId, "guildId must not be null");
    }
}
