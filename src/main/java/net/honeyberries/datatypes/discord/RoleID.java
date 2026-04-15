package net.honeyberries.datatypes.discord;

import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.Role;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;

import java.util.List;
import java.util.Objects;

/**
 * Strongly typed wrapper for a Discord role snowflake.
 * Keeps role identifiers distinct from other ids and concentrates conversion logic in one place.
 */
public record RoleID(long value) {

    /**
     * Creates a {@code RoleID} from a JDA {@link Role}.
     *
     * @param role role entity providing the interactionID; must not be {@code null}
     * @return identifier corresponding to the provided role
     * @throws NullPointerException if {@code role} is {@code null}
     */
    @NotNull
    public static RoleID fromRole(@NotNull Role role) {
        Objects.requireNonNull(role, "role must not be null");
        return new RoleID(role.getIdLong());
    }


    /**
     * Converts a list of {@link Role} objects into a list of {@link RoleID} objects.
     *
     * @param roles the list of {@link Role} objects to be converted; must not be {@code null}
     * @return a list of {@link RoleID} objects corresponding to the provided roles
     * @throws NullPointerException if {@code roles} is {@code null}
     */
    @NotNull
    public static List<RoleID> fromRoles(@NotNull List<Role> roles) {
        Objects.requireNonNull(roles, "roles must not be null");
        return roles.stream().map(RoleID::fromRole).toList();
    }


    /**
     * Returns the snowflake identifier rendered as an unsigned decimal string.
     *
     * @return unsigned decimal representation of the role interactionID
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