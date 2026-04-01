package net.honeyberries.datatypes.discord;

import net.dv8tion.jda.api.entities.User;
import net.honeyberries.discord.JDAManager;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;

import java.util.Objects;

/**
 * Strongly typed wrapper for a Discord user snowflake.
 * Ensures user identifiers remain distinct from other ids and centralizes conversion logic.
 */
public record UserID(long value) {

    /**
     * Creates a {@code UserID} from a JDA {@link User}.
     *
     * @param user user entity to extract the snowflake from; must not be {@code null}
     * @return identifier tied to the provided user
     * @throws NullPointerException if {@code user} is {@code null}
     */
    @NotNull
    public static UserID fromUser(@NotNull User user) {
        Objects.requireNonNull(user, "user must not be null");
        return new UserID(user.getIdLong());
    }

    /**
     * Parses an unsigned snowflake string into a {@code UserID}.
     *
     * @param string user snowflake as text; must not be {@code null}
     * @throws NumberFormatException if the string cannot be parsed
     * @throws NullPointerException  if {@code string} is {@code null}
     */
    public UserID(@NotNull String string) {
        Objects.requireNonNull(string, "string must not be null");
        long id = Long.parseLong(string);
        this(id);
    }


    /**
     * Resolves the current {@code UserID} to its corresponding Discord user in JDA.
     * @return the {@link User} associated with the stored identifier, or {@code null} if no such user exists
     */
    @Nullable
    public User toUser() {
        return JDAManager.getInstance().getJDA().retrieveUserById(value).complete();
    }


    /**
     * Returns the snowflake identifier rendered as an unsigned decimal string.
     *
     * @return unsigned decimal representation of the user id
     */
    @NotNull
    @Override
    public String toString() {
        return Long.toUnsignedString(value);
    }
}

