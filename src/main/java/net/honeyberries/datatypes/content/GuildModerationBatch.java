package net.honeyberries.datatypes.content;

import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import org.jetbrains.annotations.NotNull;

import java.util.List;
import java.util.Map;
import java.util.Objects;

/**
 * Aggregates all moderation-relevant content for a guild into a single payload sent to the AI.
 * Holds current messages grouped by channel, the users involved, and a separate set of historical users for context enrichment.
 * The batch allows downstream components to serialize a complete snapshot of the guild state without re-querying Discord.
 */
public record GuildModerationBatch(
        @NotNull GuildID guildId,
        @NotNull String guildName,
        @NotNull Map<ChannelID, ChannelContext> channels,
        @NotNull List<ModerationUser> users,
        @NotNull List<ModerationUser> historyUsers
) {
    /**
     * Compact constructor enforcing required references.
     *
     * @param guildId      guild being moderated; must not be {@code null}
     * @param guildName    display name of the guild; must not be {@code null}
     * @param channels     channel-to-context map for current messages; must not be {@code null}
     * @param users        active users involved in the current moderation batch; must not be {@code null}
     * @param historyUsers historical users providing additional context; must not be {@code null}
     * @throws NullPointerException if any non-nullable argument is {@code null}
     */
    public GuildModerationBatch {
        Objects.requireNonNull(guildId, "guildId must not be null");
        Objects.requireNonNull(guildName, "guildName must not be null");
        Objects.requireNonNull(channels, "channels must not be null");
        Objects.requireNonNull(users, "users must not be null");
        Objects.requireNonNull(historyUsers, "historyUsers must not be null");
    }

    /**
     * Convenience constructor with empty channels and users.
     *
     * @param guildId   guild being moderated; must not be {@code null}
     * @param guildName display name of the guild; must not be {@code null}
     * @throws NullPointerException if any required argument is {@code null}
     */
    public GuildModerationBatch(
            @NotNull GuildID guildId,
            @NotNull String guildName
    ) {
        this(guildId, guildName, Map.of(), List.of(), List.of());
    }

    /**
     * Determines whether there is any actionable content in the batch.
     *
     * @return {@code true} if no users exist or all users have empty channel lists; {@code false} otherwise
     */
    public boolean isEmpty() {
        return users.isEmpty() || users.stream().allMatch(u -> u.channels().isEmpty());
    }
}
