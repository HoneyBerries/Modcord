package net.honeyberries.ui;

import net.dv8tion.jda.api.EmbedBuilder;
import net.dv8tion.jda.api.components.actionrow.ActionRow;
import net.dv8tion.jda.api.components.buttons.Button;
import net.dv8tion.jda.api.components.label.Label;
import net.dv8tion.jda.api.components.selections.StringSelectMenu;
import net.dv8tion.jda.api.components.textinput.TextInput;
import net.dv8tion.jda.api.components.textinput.TextInputStyle;
import net.dv8tion.jda.api.entities.User;
import net.dv8tion.jda.api.modals.Modal;
import net.dv8tion.jda.api.utils.messages.MessageCreateBuilder;
import net.dv8tion.jda.api.utils.messages.MessageCreateData;
import net.honeyberries.datatypes.action.ActionData;
import net.honeyberries.datatypes.action.ActionType;
import net.honeyberries.datatypes.action.AppealData;
import net.honeyberries.datatypes.discord.UserID;
import net.honeyberries.util.ActionHelper;
import net.honeyberries.util.DiscordUtils;
import org.jetbrains.annotations.NotNull;

import java.awt.*;
import java.time.Instant;
import java.util.List;
import java.util.Objects;

public class AppealEmbedUI {

    /**
     * Builds a rich appeal notification embed with Accept/Reject buttons for moderators.
     * Displays the appellant, original action details, and the appeal reason.
     *
     * @param appeal the appeal data with embedded action info, must not be {@code null}
     * @param appellant the user who submitted the appeal, must not be {@code null}
     * @return a {@code MessageCreateData} with the embed and action buttons
     */
    @NotNull
    public static MessageCreateData buildAppealEmbedForAdmins(
            @NotNull AppealData appeal,
            @NotNull User appellant) {
        Objects.requireNonNull(appeal, "appeal must not be null");
        Objects.requireNonNull(appellant, "appellant must not be null");

        EmbedBuilder embed = buildAppealEmbedCore(appeal, appellant);

        Button acceptBtn = Button.success("appeal:accept:" + appeal.id(), "✅ Accept");
        Button rejectBtn = Button.danger("appeal:reject:" + appeal.id(), "❌ Reject");

        return new MessageCreateBuilder()
                .setEmbeds(embed.build())
                .addComponents(ActionRow.of(acceptBtn, rejectBtn))
                .build();
    }

    /**
     * Builds a rich appeal notification embed without buttons (for sending to the appellant via DM).
     * Displays the appellant, original action details, and the appeal reason.
     *
     * @param appeal the appeal data with embedded action info, must not be {@code null}
     * @param appellant the user who submitted the appeal, must not be {@code null}
     * @return a {@code MessageCreateData} with the embed and no components
     */
    @NotNull
    public static MessageCreateData buildAppealEmbedForAppellant(
            @NotNull AppealData appeal,
            @NotNull User appellant) {
        Objects.requireNonNull(appeal, "appeal must not be null");
        Objects.requireNonNull(appellant, "appellant must not be null");

        EmbedBuilder embed = buildAppealEmbedCore(appeal, appellant);

        return new MessageCreateBuilder()
                .setEmbeds(embed.build())
                .build();
    }

    /**
     * Shared builder for the appeal notification embed (fields, styling, duration handling)
     * used by both the admin (with buttons) and appellant (no buttons) variants.
     *
     * @param appeal the appeal data with embedded action info, must not be {@code null}
     * @param appellant the user who submitted the appeal, must not be {@code null}
     * @return an {@code EmbedBuilder} populated with the common appeal notification fields
     */
    @NotNull
    private static EmbedBuilder buildAppealEmbedCore(
            @NotNull AppealData appeal,
            @NotNull User appellant) {
        ActionData action = appeal.actionData();
        UserID appellantId = UserID.fromUser(appellant);

        EmbedBuilder embed = new EmbedBuilder()
                .setTitle(ActionHelper.actionEmoji(action.action()) + " Appeal — " + action.action().name())
                .setColor(Color.CYAN)
                .setTimestamp(appeal.submittedTimestamp())
                .addField("Appellant", DiscordUtils.userMention(appellantId), true)
                .addField("Moderator", DiscordUtils.userMention(action.moderatorId()), true)
                .addField("Action Type", action.action().name(), true)
                .addField("Original Reason", action.reason(), false)
                .addField("Appeal Reason", appeal.reason(), false)
                .setThumbnail(appellant.getEffectiveAvatarUrl())
                .setFooter("Appeal ID: " + appeal.id());

        EmbedHelper.addDurationField(embed, action.action(), action.timestamp(),
                action.action() == ActionType.TIMEOUT ? action.timeoutDuration() : action.banDuration(),
                "Duration");

        return embed;
    }

    /**
     * Builds the action row components for the appeal action select menu.
     *
     * @param actions list of moderation actions to choose from
     * @param isDM true if the command was invoked in a DM (so guild names are shown)
     * @return a list of action rows with the select menu
     */
    @NotNull
    public static List<ActionRow> buildActionSelectComponents(
            @NotNull List<ActionData> actions,
            boolean isDM) {
        Objects.requireNonNull(actions, "actions must not be null");

        StringSelectMenu.Builder menuBuilder = StringSelectMenu.create("appeal_action_select")
                .setPlaceholder("Select an action to appeal");

        for (ActionData action : actions) {
            String actionTypeStr = action.action().toString().toUpperCase();
            String truncatedReason = DiscordUtils.truncate(action.reason(), 40);
            String label;

            if (action.guildId().toGuild() == null) {
                label = actionTypeStr + " (DM)";

            } else if (isDM) {
                label = actionTypeStr + " (from " + Objects.requireNonNull(action.guildId().toGuild()).getName() + " — " + truncatedReason + ")";

            } else {
                label = actionTypeStr + " — " + truncatedReason;
            }

            menuBuilder.addOption(label, action.id().toString());
        }

        StringSelectMenu menu = menuBuilder.build();
        return List.of(ActionRow.of(menu));
    }

    /**
     * Builds a modal for the user to submit their appeal reason.
     *
     * @param actionId the UUID of the action being appealed
     * @return a Modal with a text input for the appeal reason
     */
    @NotNull
    public static Modal buildAppealModal(@NotNull String actionId) {
        Objects.requireNonNull(actionId, "actionId must not be null");

        TextInput reasonInput = TextInput.create("reason", TextInputStyle.PARAGRAPH)
                .setMinLength(20)
                .setMaxLength(1000)
                .setRequired(true)
                .setPlaceholder("Explain why you believe this action should be reversed...")
                .build();

        Label reasonLabel = Label.of("Why are you appealing?", reasonInput);

        return Modal.create("appeal:submit:" + actionId, "Submit Appeal")
                .addComponents(reasonLabel)
                .build();
    }

    /**
     * Builds a rich approval confirmation embed sent to the appellant via DM.
     *
     * @param appeal the appeal data with embedded action info, must not be {@code null}
     * @param resolvedBy the moderator who approved the appeal, must not be {@code null}
     * @return a {@code MessageCreateData} with the approval embed
     */
    @NotNull
    public static MessageCreateData buildApprovalDmEmbed(
            @NotNull AppealData appeal,
            @NotNull User resolvedBy) {
        return buildAppealDecisionEmbed(appeal, resolvedBy, "✅ Appeal Approved", Color.GREEN);
    }

    /**
     * Builds a rich rejection confirmation embed sent to the appellant via DM.
     *
     * @param appeal the appeal data with embedded action info, must not be {@code null}
     * @param resolvedBy the moderator who rejected the appeal, must not be {@code null}
     * @return a {@code MessageCreateData} with the rejection embed
     */
    @NotNull
    public static MessageCreateData buildRejectionDmEmbed(
            @NotNull AppealData appeal,
            @NotNull User resolvedBy) {
        return buildAppealDecisionEmbed(appeal, resolvedBy, "❌ Appeal Rejected", Color.RED);
    }

    /**
     * Shared builder for appeal decision embeds (approval/rejection).
     */
    @NotNull
    private static MessageCreateData buildAppealDecisionEmbed(
            @NotNull AppealData appeal,
            @NotNull User resolvedBy,
            @NotNull String title,
            @NotNull Color color) {
        Objects.requireNonNull(appeal, "appeal must not be null");
        Objects.requireNonNull(resolvedBy, "resolvedBy must not be null");
        Objects.requireNonNull(title, "title must not be null");
        Objects.requireNonNull(color, "color must not be null");

        ActionData action = appeal.actionData();

        EmbedBuilder embed = new EmbedBuilder()
                .setTitle(title)
                .setColor(color)
                .setTimestamp(Instant.now())
                .addField("Action Type", ActionHelper.actionEmoji(action.action()) + " " + action.action().name(), true)
                .addField("Original Reason", action.reason(), false)
                .addField("Appeal Reason", appeal.reason(), false)
                .addField("Resolved By", DiscordUtils.userMention(UserID.fromUser(resolvedBy)), true)
                .setThumbnail(resolvedBy.getEffectiveAvatarUrl())
                .setFooter("Appeal ID: " + appeal.id());

        EmbedHelper.addDurationField(embed, action.action(), action.timestamp(),
                action.action() == ActionType.TIMEOUT ? action.timeoutDuration() : action.banDuration(),
                "Duration");

        return new MessageCreateBuilder()
                .setEmbeds(embed.build())
                .build();
    }

    /**
     * Builds an embed reflecting a resolved appeal (accepted/rejected), for editing the original
     * appeal notification message in place. Unlike {@link #buildAppealEmbedForAdmins}, this omits
     * the appellant's avatar thumbnail and duration field, and adds a "Resolved by" field instead
     * of action buttons.
     *
     * @param appeal the appeal data with embedded action info, must not be {@code null}
     * @param resolvedBy the moderator who resolved the appeal, must not be {@code null}
     * @param title the resolution title (e.g., "✅ Appeal Accepted"), must not be {@code null}
     * @param color the embed color, must not be {@code null}
     * @return an {@code EmbedBuilder} populated with the resolved appeal fields
     */
    @NotNull
    public static EmbedBuilder buildResolvedAppealEmbed(
            @NotNull AppealData appeal,
            @NotNull User resolvedBy,
            @NotNull String title,
            @NotNull Color color) {
        Objects.requireNonNull(appeal, "appeal must not be null");
        Objects.requireNonNull(resolvedBy, "resolvedBy must not be null");
        Objects.requireNonNull(title, "title must not be null");
        Objects.requireNonNull(color, "color must not be null");

        ActionData action = appeal.actionData();

        return new EmbedBuilder()
                .setTitle(title)
                .setColor(color)
                .setTimestamp(appeal.submittedTimestamp())
                .addField("Appellant", DiscordUtils.userMention(appeal.userId()), true)
                .addField("Moderator", DiscordUtils.userMention(action.moderatorId()), true)
                .addField("Action Type", action.action().name(), true)
                .addField("Original Reason", action.reason(), false)
                .addField("Appeal Reason", appeal.reason(), false)
                .addField("Resolved by", DiscordUtils.userMention(UserID.fromUser(resolvedBy)), true)
                .setFooter("Appeal ID: " + appeal.id());
    }

}
