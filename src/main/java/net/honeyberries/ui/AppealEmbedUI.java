package net.honeyberries.ui;

import net.dv8tion.jda.api.EmbedBuilder;
import net.dv8tion.jda.api.components.actionrow.ActionRow;
import net.dv8tion.jda.api.components.label.Label;
import net.dv8tion.jda.api.components.selections.StringSelectMenu;
import net.dv8tion.jda.api.components.textinput.TextInput;
import net.dv8tion.jda.api.components.textinput.TextInputStyle;
import net.dv8tion.jda.api.entities.User;
import net.dv8tion.jda.api.modals.Modal;
import net.honeyberries.datatypes.action.ActionData;
import net.honeyberries.datatypes.discord.UserID;
import net.honeyberries.util.DiscordUtils;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;

import java.awt.Color;
import java.time.Instant;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

public class AppealEmbedUI {

    /**
     * Builds an embed notification for a new moderation appeal to be posted in the audit log channel.
     *
     * @param appellant the user who submitted the appeal
     * @param appealId the UUID of the appeal
     * @param actionId the UUID of the action being appealed, may be null
     * @param reason the appeal text
     * @return an embed builder ready to be built
     */
    @NotNull
    public static EmbedBuilder buildAppealNotificationEmbed(
            @NotNull User appellant,
            @NotNull UUID appealId,
            @Nullable UUID actionId,
            @NotNull String reason) {
        Objects.requireNonNull(appellant, "appellant must not be null");
        Objects.requireNonNull(appealId, "appealId must not be null");
        Objects.requireNonNull(reason, "reason must not be null");

        UserID userId = UserID.fromUser(appellant);
        EmbedBuilder embed = new EmbedBuilder()
                .setTitle("📋 New Moderation Appeal")
                .setColor(Color.CYAN)
                .setTimestamp(Instant.now())
                .addField("Appellant", DiscordUtils.userMention(userId), true)
                .addField("Appeal ID", "`" + appealId + "`", true);

        if (actionId != null) {
            embed.addField("Action ID", "`" + actionId + "`", true);
        }

        embed.addField("Reason", reason, false)
                .setThumbnail(appellant.getEffectiveAvatarUrl())
                .setFooter("Use /appeal close " + appealId + " to resolve", null);

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
                label = actionTypeStr + " (from " + action.guildId().toGuild().getName() + " — " + truncatedReason + ")";

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


}
