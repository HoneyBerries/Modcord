package net.honeyberries.util;

import net.dv8tion.jda.api.Permission;
import net.dv8tion.jda.api.entities.Member;
import net.honeyberries.database.repository.SpecialUsersRepository;
import net.honeyberries.datatypes.discord.UserID;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;

public class DiscordUtils {

    /**
     * Determines whether the provided member has administrative privileges.
     * A member is considered an administrator if they explicitly have the
     * {@link Permission#ADMINISTRATOR} permission or are listed as a special user
     * in the global backdoor repository.
     *
     * @param member the member to check for administrative privileges; may be {@code null}
     * @return {@code true} if the member has administrative privileges, {@code false} otherwise
     */
    public static boolean isAdmin(@Nullable Member member) {
        return member != null && (member.hasPermission(Permission.ADMINISTRATOR)
                || SpecialUsersRepository.getInstance().isSpecialUser(member.getUser()));
    }

    /**
     * Returns the Discord mention string for a user ID (e.g., "<@12345>").
     *
     * @param userId the user ID to mention, must not be {@code null}
     * @return a formatted mention string
     */
    @NotNull
    public static String userMention(@NotNull UserID userId) {
        return "<@" + userId.value() + ">";
    }

    /**
     * Truncates a string to the given max length, appending "…" if shortened.
     *
     * @param text   the string to truncate, must not be {@code null}
     * @param maxLen maximum length before truncation
     * @return the (possibly truncated) string
     */
    @NotNull
    public static String truncate(@NotNull String text, int maxLen) {
        if (text.length() <= maxLen) return text;
        return text.substring(0, maxLen - 1) + "…";
    }

}
