package net.honeyberries.datatypes.action;

import org.jetbrains.annotations.NotNull;

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
}
