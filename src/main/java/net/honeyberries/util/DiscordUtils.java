package net.honeyberries.util;

import net.dv8tion.jda.api.Permission;
import net.dv8tion.jda.api.entities.Member;
import net.honeyberries.database.repository.SpecialUsersRepository;
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

}
