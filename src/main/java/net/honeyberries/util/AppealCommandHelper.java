package net.honeyberries.util;

import net.dv8tion.jda.api.JDA;
import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.User;
import net.dv8tion.jda.api.events.interaction.ModalInteractionEvent;
import net.dv8tion.jda.api.events.interaction.command.SlashCommandInteractionEvent;
import net.dv8tion.jda.api.events.interaction.component.StringSelectInteractionEvent;
import net.honeyberries.database.repository.AppealRepository;
import net.honeyberries.database.repository.GuildModerationActionsRepository;
import net.honeyberries.datatypes.action.ActionData;
import net.honeyberries.datatypes.action.ActionType;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.discord.UserID;
import net.honeyberries.ui.AppealEmbedUI;
import org.jetbrains.annotations.NotNull;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.*;
import java.util.stream.Collectors;

public class AppealCommandHelper {

    private static final Logger logger = LoggerFactory.getLogger(AppealCommandHelper.class);
    private final GuildModerationActionsRepository actionRepository = GuildModerationActionsRepository.getInstance();
    private final AppealRepository appealRepository = AppealRepository.getInstance();

    /**
     * Handles /appeal submit by fetching the user's moderation actions and presenting them in a select menu.
     * Works in both guild channels and DMs.
     */
    public void handleShowActionSelect(@NotNull SlashCommandInteractionEvent event) {
        User user = event.getUser();
        UserID userId = UserID.fromUser(user);

        // Determine context: guild or DM
        boolean isDM = event.getGuild() == null;
        List<ActionData> allActions = new ArrayList<>();
        Set<UUID> alreadyAppealedIds = new HashSet<>();

        if (isDM) {
            // DM context: fetch all actions for this user from the database
            // (can't use mutual guilds since banned users won't appear there)
            allActions.addAll(actionRepository.getAllActionsByUser(userId));

            // Also collect all appealed action IDs from database
            alreadyAppealedIds.addAll(appealRepository.getAllOpenAppealActionIds(userId));
        } else {
            // Guild context: fetch actions for this specific guild
            GuildID guildId = new GuildID(event.getGuild().getIdLong());
            allActions.addAll(actionRepository.getActionsByUser(guildId, userId));

            // Collect already-appealed action IDs for this guild
            List<UUID> appealedIds = appealRepository.getOpenAppealActionIds(guildId, userId);
            alreadyAppealedIds.addAll(appealedIds);
        }

        // Filter: keep only BAN, KICK, WARN, TIMEOUT; remove already-appealed actions
        List<ActionData> eligibleActions = allActions.stream()
                .filter(action -> isAppealableActionType(action.action()))
                .filter(action -> !alreadyAppealedIds.contains(action.id()))
                .toList();

        if (eligibleActions.isEmpty()) {
            event.reply("You have no recorded actions to appeal.")
                    .setEphemeral(true)
                    .queue();
            return;
        }

        // Limit to 25 options (Discord select menu limit)
        List<ActionData> actionsToShow = eligibleActions.stream()
                .limit(25)
                .collect(Collectors.toList());

        event.reply("Select an action to appeal below:")
                .setComponents(AppealEmbedUI.buildActionSelectComponents(actionsToShow, isDM))
                .setEphemeral(true)
                .queue();
    }

    /**
     * Handles the select menu interaction when a user picks an action to appeal.
     */
    public void handleActionSelect(@NotNull StringSelectInteractionEvent event) {
        String selectedActionId = event.getValues().getFirst();

        event.replyModal(AppealEmbedUI.buildAppealModal(selectedActionId))
                .queue();
    }

    /**
     * Handles the modal submission for the appeal reason.
     */
    public void handleModalSubmit(@NotNull ModalInteractionEvent event) {
        String modalId = event.getModalId();

        // Parse action ID from modal custom ID: "appeal:submit:<uuid>"
        String[] parts = modalId.split(":");
        if (parts.length < 3) {
            event.reply("Invalid appeal modal ID.").setEphemeral(true).queue();
            logger.warn("Modal ID format incorrect: {}", modalId);
            return;
        }

        UUID actionId;
        try {
            actionId = UUID.fromString(parts[2]);
        } catch (IllegalArgumentException e) {
            event.reply("Invalid action ID format.").setEphemeral(true).queue();
            logger.warn("Failed to parse action ID from modal: {}", parts[2], e);
            return;
        }

        // Fetch the action to validate and extract guild ID
        ActionData action = actionRepository.getActionById(actionId);
        if (action == null) {
            event.reply("The action you are appealing no longer exists.").setEphemeral(true).queue();
            return;
        }

        // Extract reason from modal input
        String reason = Objects.requireNonNull(event.getValue("reason")).getAsString();

        // Create the appeal
        UserID userId = UserID.fromUser(event.getUser());
        UUID appealId = appealRepository.createAppeal(action.guildId(), userId.value(), actionId, reason);

        if (appealId == null) {
            event.reply("Failed to submit appeal. Please try again later.").setEphemeral(true).queue();
            logger.error("Failed to create appeal for user {} on action {}", userId.value(), actionId);
            return;
        }

        // Notify moderators
        Guild guild = event.getJDA().getGuildById(action.guildId().value());
        if (guild != null) {
            notifyModerators(event.getJDA(), guild, userId, appealId, actionId, reason);
        } else {
            logger.warn("Guild {} not found for appeal notification", action.guildId().value());
        }

        event.reply("Your appeal has been submitted. Appeal ID: `" + appealId + "`").setEphemeral(true).queue();
    }

    /**
     * Sends a notification to moderators in the audit log channel.
     */
    private void notifyModerators(
            @NotNull JDA jda,
            @NotNull Guild guild,
            @NotNull UserID userId,
            @NotNull UUID appealId,
            @NotNull UUID actionId,
            @NotNull String reason) {
        User user = jda.retrieveUserById(userId.value()).complete();
        if (user == null) {
            logger.warn("User {} not found for appeal notification", userId.value());
            return;
        }

        try {
            guild.getTextChannels().stream()
                    .filter(channel -> channel.getName().equals("audit-log"))
                    .findFirst()
                    .ifPresentOrElse(
                            channel -> channel.sendMessageEmbeds(
                                    AppealEmbedUI.buildAppealNotificationEmbed(user, appealId, actionId, reason).build()
                            ).queue(),
                            () -> logger.warn("Audit log channel not found in guild {}", guild.getId())
                    );
        } catch (Exception e) {
            logger.error("Failed to notify moderators of appeal {} in guild {}", appealId, guild.getId(), e);
        }
    }

    /**
     * Checks if an action type can be appealed.
     */
    private boolean isAppealableActionType(@NotNull ActionType actionType) {
        return actionType == ActionType.BAN
                || actionType == ActionType.KICK
                || actionType == ActionType.TIMEOUT;
    }
}
