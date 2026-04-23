package net.honeyberries.ui;

import net.dv8tion.jda.api.EmbedBuilder;
import net.dv8tion.jda.api.entities.User;
import net.dv8tion.jda.api.utils.messages.MessageCreateBuilder;
import net.dv8tion.jda.api.utils.messages.MessageCreateData;
import net.dv8tion.jda.api.utils.TimeFormat;
import net.honeyberries.datatypes.action.ActionData;
import net.honeyberries.datatypes.action.ActionType;
import net.honeyberries.datatypes.discord.UserID;
import net.honeyberries.util.ActionHelper;
import net.honeyberries.util.DiscordUtils;
import org.jetbrains.annotations.NotNull;

import java.awt.Color;
import java.time.Instant;
import java.util.Objects;

public class ActionEmbedUI {

    /**
     * Constructs a rich embed notification for a moderation action, including user details,
     * moderator, reason, and duration info.
     *
     * @param actionData the action details
     * @param target the target user of the action
     * @return a {@code MessageCreateData} containing the formatted embed
     */
    @NotNull
    public static MessageCreateData buildNotificationEmbed(@NotNull ActionData actionData, @NotNull User target) {
        Objects.requireNonNull(actionData, "actionData must not be null");
        Objects.requireNonNull(target, "target must not be null");

        UserID targetId = UserID.fromUser(target);
        EmbedBuilder embed = new EmbedBuilder()
                .setTitle(ActionHelper.actionEmoji(actionData.action()) + " " + actionData.action().name() + " Issued")
                .setColor(ActionHelper.actionColor(actionData.action()))
                .setTimestamp(Instant.now())
                .addField("User", DiscordUtils.userMention(targetId), true)
                .addField("Moderator", DiscordUtils.userMention(actionData.moderatorId()), true)
                .addField("Reason", actionData.reason(), false)
                .setThumbnail(target.getEffectiveAvatarUrl())
                .setFooter("Action ID: " + actionData.id());

        if (actionData.action() == ActionType.TIMEOUT && actionData.timeoutDuration() > 0) {
            Instant expiresAt = Instant.now().plusSeconds(actionData.timeoutDuration());
            embed.addField("Duration",
                    formatDuration(actionData.timeoutDuration()) + " — expires " + TimeFormat.RELATIVE.format(expiresAt),
                    false);
        }

        if (actionData.action() == ActionType.BAN && actionData.banDuration() > 0) {
            if (actionData.banDuration() >= Integer.MAX_VALUE) {
                embed.addField("Duration", "Permanent", false);
            } else {
                Instant expiresAt = Instant.now().plusSeconds(actionData.banDuration());
                embed.addField("Duration",
                        formatDuration(actionData.banDuration()) + " — expires " + TimeFormat.RELATIVE.format(expiresAt),
                        false);
            }
        }

        return new MessageCreateBuilder().setEmbeds(embed.build()).build();
    }

    /**
     * Formats a duration in seconds into a human-readable string (e.g., "1d 2h 30m").
     *
     * @param seconds the duration in seconds
     * @return a formatted duration string
     */
    @NotNull
    private static String formatDuration(long seconds) {
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

}
