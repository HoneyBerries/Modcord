package net.honeyberries.datatypes.action;

import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;

import java.util.Objects;

/**
 * Enumerates the moderation operations that can be issued by the AI and executed by the bot.
 * Each constant carries the raw value expected by downstream consumers so serialization and display stay consistent.
 */
public enum ActionType {
    BAN("ban"),
    UNBAN("unban"),
    KICK("kick"),
    WARN("warn"),
    DELETE("delete"),
    TIMEOUT("timeout"),
    NULL("null");

    private final String value;

    ActionType(@NotNull String value) {
        this.value = Objects.requireNonNull(value, "value must not be null");
    }

    /**
     * Returns the raw token representation of the action, used in prompts and persistence.
     *
     * @return non-null action token
     */
    @NotNull
    @Override
    public String toString() {
        return value;
    }

    /**
     * Exposes the stored token string for serialization.
     *
     * @return non-null action token
     */
    @NotNull
    public String getValue() {
        return value;
    }


    /**
     * Parses a user-supplied action string into an {@link ActionType}.
     *
     * <p>Matching is case-insensitive and trims surrounding whitespace.
     *
     * @param actionStr the raw string from the slash command option; must not be null
     * @return the matching {@link ActionType}, or {@code null} if unrecognised
     */
    @Nullable
    public static ActionType parseActionType(@NotNull String actionStr) {
        Objects.requireNonNull(actionStr, "actionStr must not be null");
        return switch (actionStr.toLowerCase().strip()) {
            case "warn"    -> ActionType.WARN;
            case "timeout" -> ActionType.TIMEOUT;
            case "delete"  -> ActionType.DELETE;
            case "kick"    -> ActionType.KICK;
            case "ban"     -> ActionType.BAN;
            case "unban"   -> ActionType.UNBAN;
            default        -> null;
        };
    }
}
