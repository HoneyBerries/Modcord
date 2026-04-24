package net.honeyberries.ui;

import net.dv8tion.jda.api.EmbedBuilder;
import net.dv8tion.jda.api.components.buttons.Button;
import net.dv8tion.jda.api.components.actionrow.ActionRow;
import net.dv8tion.jda.api.components.label.Label;
import net.dv8tion.jda.api.components.selections.StringSelectMenu;
import net.dv8tion.jda.api.components.textinput.TextInput;
import net.dv8tion.jda.api.components.textinput.TextInputStyle;
import net.dv8tion.jda.api.entities.User;
import net.dv8tion.jda.api.modals.Modal;
import net.dv8tion.jda.api.utils.TimeFormat;
import net.dv8tion.jda.api.utils.messages.MessageCreateBuilder;
import net.dv8tion.jda.api.utils.messages.MessageCreateData;
import net.honeyberries.datatypes.action.ActionData;
import net.honeyberries.datatypes.action.ActionType;
import net.honeyberries.datatypes.action.AppealData;
import net.honeyberries.datatypes.discord.UserID;
import net.honeyberries.util.ActionHelper;
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
     * Builds a rich appeal notification embed with Accept/Reject buttons for moderators.
     * Displays the appellant, original action details, and the appeal reason.
     *
     * @param appeal the appeal data with embedded action info, must not be {@code null}
     * @param appellant the user who submitted the appeal, must not be {@code null}
     * @return a {@code MessageCreateData} with the embed and action buttons
     */
    @NotNull
    public static MessageCreateData buildAppealNotificationEmbed(
            @NotNull AppealData appeal,
            @NotNull User appellant) {
        Objects.requireNonNull(appeal, "appeal must not be null");
        Objects.requireNonNull(appellant, "appellant must not be null");

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

        if (action.action() == ActionType.TIMEOUT && action.timeoutDuration() > 0) {
            Instant expiresAt = action.timestamp().plusSeconds(action.timeoutDuration());
            embed.addField("Duration",
                    formatDuration(action.timeoutDuration()) + " — expires " + TimeFormat.RELATIVE.format(expiresAt),
                    false);
        }

        if (action.action() == ActionType.BAN && action.banDuration() > 0) {
            if (action.banDuration() >= Integer.MAX_VALUE) {
                embed.addField("Duration", "Permanent", false);
            } else {
                Instant expiresAt = action.timestamp().plusSeconds(action.banDuration());
                embed.addField("Duration",
                        formatDuration(action.banDuration()) + " — expires " + TimeFormat.RELATIVE.format(expiresAt),
                        false);
            }
        }

        Button acceptBtn = Button.success("appeal:accept:" + appeal.id(), "✅ Accept");
        Button rejectBtn = Button.danger("appeal:reject:" + appeal.id(), "❌ Reject");

        return new MessageCreateBuilder()
                .setEmbeds(embed.build())
                .addComponents(ActionRow.of(acceptBtn, rejectBtn))
                .build();
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
