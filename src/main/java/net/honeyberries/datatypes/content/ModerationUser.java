package net.honeyberries.datatypes.content;

import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.Member;
import net.honeyberries.datatypes.discord.DiscordUser;
import net.honeyberries.datatypes.discord.UserID;
import org.jetbrains.annotations.NotNull;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Objects;

/**
 * Aggregates all moderation-relevant information about a guild member, including roles and channel activity.
 * Wraps mutable JDA entities with immutable identifiers so equality and hashing remain stable for batching and lookups.
 * Mutable {@link Member} and {@link Guild} references are intentionally excluded from equality checks to avoid churn when the entities update.
 */
public record ModerationUser(
        @NotNull UserID userId,
        @NotNull DiscordUser username,
        @NotNull LocalDateTime joinDate,
        @NotNull Member discordMember,
        @NotNull Guild discordGuild,
        @NotNull List<String> roles,
        @NotNull List<ModerationUserChannel> channels
) {
    /**
     * Validates required references and lists for the moderation user snapshot.
     *
     * @param userId        unique user identifier; must not be {@code null}
     * @param username      display username and interactionID pair; must not be {@code null}
     * @param joinDate      guild join timestamp; must not be {@code null}
     * @param discordMember live JDA member entity; must not be {@code null}
     * @param discordGuild  live JDA guild entity; must not be {@code null}
     * @param roles         role names held by the user; may be empty but not {@code null}
     * @param channels      per-channel message groupings; may be empty but not {@code null}
     * @throws NullPointerException if any required argument is {@code null}
     */
    public ModerationUser {
        Objects.requireNonNull(userId, "userId must not be null");
        Objects.requireNonNull(username, "username must not be null");
        Objects.requireNonNull(joinDate, "joinDate must not be null");
        Objects.requireNonNull(discordMember, "discordMember must not be null");
        Objects.requireNonNull(discordGuild, "discordGuild must not be null");
        Objects.requireNonNull(roles, "roles must not be null");
        Objects.requireNonNull(channels, "channels must not be null");
    }

    /**
     * Custom equals that ignores mutable JDA entities to keep comparisons stable.
     *
     * @param obj object to compare against
     * @return {@code true} when identifiers, join date, roles, and channels match
     */
    @Override
    public boolean equals(Object obj) {
        if (this == obj) return true;
        if (!(obj instanceof ModerationUser(UserID uid, DiscordUser un, LocalDateTime jd, Member _, Guild _, List<String> r, List<ModerationUserChannel> c))) return false;
        return userId.equals(uid) && username.equals(un) && joinDate.equals(jd) && roles.equals(r) && channels.equals(c);
    }

    /**
     * Hash code aligned with {@link #equals(Object)}, excluding mutable JDA entities.
     *
     * @return stable hash derived from immutable fields
     */
    @Override
    public int hashCode() {
        return Objects.hash(userId, username, joinDate, roles, channels);
    }
}
