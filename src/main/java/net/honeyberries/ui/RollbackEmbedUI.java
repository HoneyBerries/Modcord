package net.honeyberries.ui;

import net.dv8tion.jda.api.EmbedBuilder;
import net.dv8tion.jda.api.entities.User;
import net.dv8tion.jda.api.utils.TimeFormat;
import net.dv8tion.jda.api.utils.messages.MessageCreateBuilder;
import net.dv8tion.jda.api.utils.messages.MessageCreateData;
import net.honeyberries.datatypes.action.ActionData;
import net.honeyberries.datatypes.action.ActionType;
import net.honeyberries.datatypes.discord.UserID;
import net.honeyberries.util.DiscordUtils;
import org.jetbrains.annotations.NotNull;

import java.awt.Color;
import java.time.Instant;
import java.util.Objects;

public class RollbackEmbedUI {

    /**
     * Builds a rich embed for a rollback (reversal) of a moderation action.
     * Displays the target user, moderator, reason for reversal, and original action details.
     *
     * @param action the action being rolled back, must not be {@code null}
     * @param target the user affected by the rollback, must not be {@code null}
     * @param moderator the moderator who triggered the rollback, must not be {@code null}
     * @param reason the reason for the rollback, must not be {@code null}
     * @return a {@code MessageCreateData} with the rollback embed
     */
    @NotNull
    public static MessageCreateData buildRollbackEmbed(
            @NotNull ActionData action,
            @NotNull User target,
            @NotNull User moderator,
            @NotNull String reason) {
        Objects.requireNonNull(action, "action must not be null");
        Objects.requireNonNull(target, "target must not be null");
        Objects.requireNonNull(moderator, "moderator must not be null");
        Objects.requireNonNull(reason, "reason must not be null");

        UserID targetId = UserID.fromUser(target);

        EmbedBuilder embed = new EmbedBuilder()
                .setTitle("↩️ Action Reversed — " + action.action().name())
                .setColor(Color.GREEN)
                .setTimestamp(Instant.now())
                .addField("User", DiscordUtils.userMention(targetId), true)
                .addField("Moderator", DiscordUtils.userMention(action.moderatorId()), true)
                .addField("Original Reason", action.reason(), false)
                .addField("Rollback Reason", reason, false)
                .addField("Reversed By", DiscordUtils.userMention(UserID.fromUser(moderator)), true)
                .setThumbnail(target.getEffectiveAvatarUrl())
                .setFooter("Action ID: " + action.id());

        addRollbackDurationField(embed, action);

        return new MessageCreateBuilder()
                .setEmbeds(embed.build())
                .build();
    }

    /**
     * Adds the "Original Duration" field to a rollback embed with "would have expired" wording.
     */
    private static void addRollbackDurationField(@NotNull EmbedBuilder embed, @NotNull ActionData action) {
        if (action.action() == ActionType.TIMEOUT && action.timeoutDuration() > 0) {
            Instant expiresAt = action.timestamp().plusSeconds(action.timeoutDuration());
            embed.addField("Original Duration",
                    EmbedHelper.formatDuration(action.timeoutDuration()) + " — would have expired " + TimeFormat.RELATIVE.format(expiresAt),
                    false);
        } else if (action.action() == ActionType.BAN && action.banDuration() > 0) {
            if (action.banDuration() >= Integer.MAX_VALUE) {
                embed.addField("Original Duration", "Permanent", false);
            } else {
                Instant expiresAt = action.timestamp().plusSeconds(action.banDuration());
                embed.addField("Original Duration",
                        EmbedHelper.formatDuration(action.banDuration()) + " — would have expired " + TimeFormat.RELATIVE.format(expiresAt),
                        false);
            }
        }
    }

}
