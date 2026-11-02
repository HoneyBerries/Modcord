package net.honeyberries.util;

import net.dv8tion.jda.api.Permission;
import org.jetbrains.annotations.NotNull;

import java.util.ArrayList;
import java.util.EnumSet;
import java.util.List;
import java.util.Set;

/**
 * Pure helper logic for the {@code /setup} checklist.
 * Needs no network or Discord connection, so it is unit-testable.
 */
public final class SetupChecklist {

    /** Minimal view of a role used for hierarchy comparison. */
    public record RoleInfo(@NotNull String name, int position, boolean managed, boolean isPublicRole) {}

    private SetupChecklist() {}

    /**
     * Permissions the bot needs given which actions are enabled.
     *
     * @return permissions required, in a stable enum order
     */
    @NotNull
    public static Set<Permission> requiredPermissions(boolean delete, boolean timeout, boolean kick, boolean ban) {
        Set<Permission> required = EnumSet.of(Permission.VIEW_CHANNEL, Permission.MESSAGE_HISTORY,
                Permission.MESSAGE_SEND, Permission.MESSAGE_EMBED_LINKS);
        if (delete) required.add(Permission.MESSAGE_MANAGE);
        if (timeout) required.add(Permission.MODERATE_MEMBERS);
        if (kick) required.add(Permission.KICK_MEMBERS);
        if (ban) required.add(Permission.BAN_MEMBERS);
        return required;
    }

    /** Returns the required permissions that are absent from {@code granted}. */
    @NotNull
    public static List<Permission> missingPermissions(@NotNull Set<Permission> required, @NotNull Set<Permission> granted) {
        if (granted.contains(Permission.ADMINISTRATOR)) return List.of();
        List<Permission> missing = new ArrayList<>();
        for (Permission p : required) {
            if (!granted.contains(p)) missing.add(p);
        }
        return missing;
    }

    /**
     * Finds non-managed, non-public roles ranked above the bot's highest role.
     *
     * @param roles       all guild roles
     * @param botPosition position of the bot's highest role
     * @param limit       maximum number of roles to return
     * @return up to {@code limit} roles, highest first
     */
    @NotNull
    public static List<RoleInfo> rolesAboveBot(@NotNull List<RoleInfo> roles, int botPosition, int limit) {
        return roles.stream()
                .filter(r -> r.position() > botPosition && !r.managed() && !r.isPublicRole())
                .sorted((a, b) -> Integer.compare(b.position(), a.position()))
                .limit(limit)
                .toList();
    }

    /** Counts roles above the bot using the same filter as {@link #rolesAboveBot}. */
    public static long countRolesAboveBot(@NotNull List<RoleInfo> roles, int botPosition) {
        return roles.stream().filter(r -> r.position() > botPosition && !r.managed() && !r.isPublicRole()).count();
    }
}
