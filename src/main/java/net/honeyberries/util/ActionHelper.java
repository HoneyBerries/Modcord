package net.honeyberries.util;

import net.honeyberries.datatypes.action.ActionType;
import org.jetbrains.annotations.NotNull;

import java.awt.*;
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



    /**
     * Selects a color matching the action type for visual feedback in embeds.
     *
     * @param actionType the moderation action type
     * @return a {@code Color} representing the action severity/type
     */
    @NotNull
    public static Color actionColor(@NotNull ActionType actionType) {
        Objects.requireNonNull(actionType, "actionType must not be null");
        return switch (actionType) {
            case WARN            -> Color.YELLOW;
            case DELETE, TIMEOUT -> Color.ORANGE;
            case KICK            -> Color.RED;
            case BAN             -> new Color(144, 0, 0);
            case UNBAN           -> Color.GREEN;
            case NULL            -> Color.WHITE;
        };
    }

}
