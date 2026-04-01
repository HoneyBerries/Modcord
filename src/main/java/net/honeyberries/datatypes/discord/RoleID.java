package net.honeyberries.datatypes.discord;

import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.Role;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;

import java.util.Objects;

/**
 * Strongly typed wrapper for a Discord role snowflake.
 * Keeps role identifiers distinct from other ids and concentrates conversion logic in one place.
 */
public record RoleID(long value) {

    /**
     * Creates a {@code RoleID} from a JDA {@link Role}.
     *
     * @param role role entity providing the id; must not be {@code null}
     * @return identifier corresponding to the provided role
     * @throws NullPointerException if {@code role} is {@code null}
     */
    @NotNull
    public static RoleID fromRole(@NotNull Role role) {
        Objects.requireNonNull(role, "role must not be null");
        return new RoleID(role.getIdLong());
    }

    /**
     * Parses an unsigned snowflake string into a {@code RoleID}.
     *
     * @param string role snowflake as text; must not be {@code null}
     * @throws NumberFormatException if the string cannot be parsed
     * @throws NullPointerException  if {@code string} is {@code null}
     */
    public RoleID(@NotNull String string) {
        Objects.requireNonNull(string, "string must not be null");
        long id = Long.parseLong(string);
        this(id);
    }

    /**
     * Returns the snowflake identifier rendered as an unsigned decimal string.
     *
     * @return unsigned decimal representation of the role id
     */
    @NotNull
    @Override
    public String toString() {
        return Long.toUnsignedString(value);
    }

    /**
     * Convenience method to get the JDA {@link Role} from a {@link Guild}.
     *
     * @param guild the guild containing the role; must not be {@code null}
     * @return the role if found in the guild, otherwise {@code null}
     */
    @Nullable
    public Role getRole(@NotNull Guild guild) {
        Objects.requireNonNull(guild, "guild must not be null");
        return guild.getRoleById(value);
    }
}