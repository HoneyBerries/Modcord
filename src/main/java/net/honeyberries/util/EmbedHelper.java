package net.honeyberries.util;

import net.dv8tion.jda.api.EmbedBuilder;
import net.dv8tion.jda.api.components.actionrow.ActionRow;
import net.dv8tion.jda.api.components.selections.StringSelectMenu;
import net.dv8tion.jda.api.utils.TimeFormat;
import net.honeyberries.datatypes.action.ActionType;
import net.honeyberries.ui.NavPage;
import org.jetbrains.annotations.NotNull;

import java.time.Instant;
import java.util.List;

public class EmbedHelper {

    /**
     * Formats a duration in seconds into a human-readable string (e.g., "1d 2h 30m 5s").
     *
     * @param seconds the duration in seconds
     * @return a formatted duration string
     */
    @NotNull
    public static String formatDuration(long seconds) {
        long days    = seconds / 86400;
        long hours   = (seconds % 86400) / 3600;
        long minutes = (seconds % 3600) / 60;
        long secs    = seconds % 60;

        StringBuilder sb = new StringBuilder();
        if (days    > 0) sb.append(days).append("d ");
        if (hours   > 0) sb.append(hours).append("h ");
        if (minutes > 0) sb.append(minutes).append("m ");
        if (secs    > 0 || sb.isEmpty()) sb.append(secs).append("s");
        return sb.toString().trim();
    }


    /**
     * Adds duration fields to an embed for TIMEOUT or BAN actions, using a custom expiry verb phrase.
     * For TIMEOUT: shows the duration with expiration time.
     * For BAN: shows "Permanent" if infinite, otherwise shows duration with expiration.
     *
     * @param embed the embed to add fields to, must not be {@code null}
     * @param actionType the action type, must not be {@code null}
     * @param actionTimestamp the timestamp when the action was created, must not be {@code null}
     * @param duration the duration in seconds (ignored if action type doesn't support it)
     * @param fieldLabel the label for the duration field (e.g., "Duration" or "Original Duration")
     * @param expiryVerb the verb phrase preceding the relative timestamp (e.g., "expires" or "would have expired")
     */
    public static void addDurationField(
            @NotNull EmbedBuilder embed,
            @NotNull ActionType actionType,
            @NotNull Instant actionTimestamp,
            long duration,
            @NotNull String fieldLabel,
            @NotNull String expiryVerb) {

        if (actionType == ActionType.TIMEOUT && duration > 0) {
            Instant expiresAt = actionTimestamp.plusSeconds(duration);
            embed.addField(fieldLabel,
                    formatDuration(duration) + " — " + expiryVerb + " " + TimeFormat.RELATIVE.format(expiresAt),
                    false);
        } else if (actionType == ActionType.BAN && duration > 0) {
            if (duration >= Integer.MAX_VALUE) {
                embed.addField(fieldLabel, "Permanent", false);
            } else {
                Instant expiresAt = actionTimestamp.plusSeconds(duration);
                embed.addField(fieldLabel,
                        formatDuration(duration) + " — " + expiryVerb + " " + TimeFormat.RELATIVE.format(expiresAt),
                        false);
            }
        }
    }

    /**
     * Builds a single-row select menu for switching between embed pages.
     *
     * @param menuId  the component ID the click handler matches on
     * @param current the {@link NavPage#value()} of the page being shown
     * @param pages   the pages to offer, in display order
     * @return an action row containing the menu
     */
    @NotNull
    public static ActionRow navigationRow(@NotNull String menuId, @NotNull String current, @NotNull List<NavPage> pages) {
        StringSelectMenu.Builder menu = StringSelectMenu.create(menuId);
        pages.forEach(p -> menu.addOption(p.label(), p.value(), p.description()));
        return ActionRow.of(menu.setDefaultValues(current).build());
    }

}
