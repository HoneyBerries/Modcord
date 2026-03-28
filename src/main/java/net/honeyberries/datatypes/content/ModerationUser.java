package net.honeyberries.datatypes.content;

import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.Member;
import net.honeyberries.datatypes.discord.DiscordUsername;
import net.honeyberries.datatypes.discord.UserID;
import org.jetbrains.annotations.NotNull;

import java.time.LocalDateTime;
import java.util.List;

/**
 * A user and their messages in a guild that are subject to moderation.
 * <p>
 * Note: discordMember and discordGuild are excluded from equals() and hashCode()
 * comparisons as they are mutable JDA entity objects.
 */
public record ModerationUser(
        @NotNull UserID userId,
        @NotNull DiscordUsername username,
        @NotNull LocalDateTime joinDate,
        @NotNull Member discordMember,
        @NotNull Guild discordGuild,
        @NotNull List<String> roles,
        @NotNull List<ModerationUserChannel> channels
) {
    /**
     * Custom equals that excludes discordMember and discordGuild.
     */
    @Override
    public boolean equals(Object obj) {
        if (this == obj) return true;
        if (!(obj instanceof ModerationUser(UserID uid, DiscordUsername un, LocalDateTime jd, Member _, Guild _, List<String> r, List<ModerationUserChannel> c))) return false;
        return userId.equals(uid) && username.equals(un) && joinDate.equals(jd) && roles.equals(r) && channels.equals(c);
    }

    /**
     * Custom hashCode that excludes discordMember and discordGuild.
     */
    @Override
    public int hashCode() {
        return java.util.Objects.hash(userId, username, joinDate, roles, channels);
    }
}

