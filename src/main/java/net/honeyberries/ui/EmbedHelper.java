package net.honeyberries.ui;

import net.dv8tion.jda.api.EmbedBuilder;
import net.dv8tion.jda.api.utils.TimeFormat;
import net.honeyberries.datatypes.action.ActionType;
import org.jetbrains.annotations.NotNull;

import java.time.Instant;

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
     * Adds duration fields to an embed for TIMEOUT or BAN actions.
     * For TIMEOUT: shows the duration with expiration time.
     * For BAN: shows "Permanent" if infinite, otherwise shows duration with expiration.
     *
     * @param embed the embed to add fields to, must not be {@code null}
     * @param actionType the action type, must not be {@code null}
     * @param actionTimestamp the timestamp when the action was created, must not be {@code null}
     * @param duration the duration in seconds (ignored if action type doesn't support it)
     * @param fieldLabel the label for the duration field (e.g., "Duration" or "Original Duration")
     */
    public static void addDurationField(
            @NotNull EmbedBuilder embed,
            @NotNull ActionType actionType,
            @NotNull Instant actionTimestamp,
            long duration,
            @NotNull String fieldLabel) {
        if (actionType == ActionType.TIMEOUT && duration > 0) {
            Instant expiresAt = actionTimestamp.plusSeconds(duration);
            embed.addField(fieldLabel,
                    formatDuration(duration) + " — expires " + TimeFormat.RELATIVE.format(expiresAt),
                    false);
        }

        if (actionType == ActionType.BAN && duration > 0) {
            if (duration >= Integer.MAX_VALUE) {
                embed.addField(fieldLabel, "Permanent", false);
            } else {
                Instant expiresAt = actionTimestamp.plusSeconds(duration);
                embed.addField(fieldLabel,
                        formatDuration(duration) + " — expires " + TimeFormat.RELATIVE.format(expiresAt),
                        false);
            }
        }
    }

}
