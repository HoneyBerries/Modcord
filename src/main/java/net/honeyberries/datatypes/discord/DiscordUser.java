package net.honeyberries.datatypes.discord;

import net.dv8tion.jda.api.entities.User;
import org.jetbrains.annotations.NotNull;

import java.util.Objects;

/**
 * Immutable pairing of a user's snowflake with their display username.
 * Encapsulates both identifiers to keep username lookups in sync with the owning {@link UserID}.
 */
public record DiscordUser(@NotNull UserID userId, @NotNull String username) {

    /**
     * Ensures required components are non-null.
     *
     * @param userId   user identifier backing the username; must not be {@code null}
     * @param username display name associated with the user; must not be {@code null}
     * @throws NullPointerException if any argument is {@code null}
     */
    public DiscordUser {
        Objects.requireNonNull(userId, "userId must not be null");
        Objects.requireNonNull(username, "username must not be null");
    }

    /**
     * Builds a {@code DiscordUser} from a JDA {@link User}.
     *
     * @param user source user whose id and display name are captured; must not be {@code null}
     * @return immutable pairing of the user's id and current name
     * @throws NullPointerException if {@code user} is {@code null}
     */
    @NotNull
    public static DiscordUser fromUser(@NotNull User user) {
        Objects.requireNonNull(user, "user must not be null");
        return new DiscordUser(new UserID(user.getIdLong()), user.getName());
    }
}
