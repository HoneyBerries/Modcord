package net.honeyberries.util;

import net.honeyberries.datatypes.action.ActionType;
import org.jetbrains.annotations.NotNull;

import java.util.Objects;

public class ActionHelper {

    /**
     * Selects an emoji matching the action type for visual feedback in embeds.
     *
     * @param actionType the moderation action type
     * @return an emoji string representing the action
     */
    @NotNull
    public static String actionEmoji(@NotNull ActionType actionType) {
        Objects.requireNonNull(actionType, "actionType must not be null");
        return switch (actionType) {
            case WARN    -> "⚠️";
            case DELETE  -> "🗑️";
            case TIMEOUT -> "⏱️";
            case KICK    -> "👢";
            case BAN     -> "🔨";
            case UNBAN   -> "✅";
            case NULL    -> "⚙️";
        };
    }

}
