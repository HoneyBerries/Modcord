package net.honeyberries.ui;

import net.dv8tion.jda.api.EmbedBuilder;
import net.dv8tion.jda.api.entities.User;
import net.dv8tion.jda.api.utils.messages.MessageCreateBuilder;
import net.dv8tion.jda.api.utils.messages.MessageCreateData;
import net.honeyberries.datatypes.action.ActionData;
import net.honeyberries.datatypes.action.ActionType;
import net.honeyberries.datatypes.discord.UserID;
import net.honeyberries.util.ActionHelper;
import net.honeyberries.util.DiscordUtils;
import org.jetbrains.annotations.NotNull;

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
                .setTimestamp(actionData.timestamp())
                .addField("User", DiscordUtils.userMention(targetId), true)
                .addField("Moderator", DiscordUtils.userMention(actionData.moderatorId()), true)
                .addField("Reason", actionData.reason(), false)
                .setThumbnail(target.getEffectiveAvatarUrl())
                .setFooter("Action ID: " + actionData.id());

        EmbedHelper.addDurationField(embed, actionData.action(), actionData.timestamp(),
                actionData.action() == ActionType.TIMEOUT ? actionData.timeoutDuration() : actionData.banDuration(),
                "Duration");

        return new MessageCreateBuilder().setEmbeds(embed.build()).build();
    }

}
