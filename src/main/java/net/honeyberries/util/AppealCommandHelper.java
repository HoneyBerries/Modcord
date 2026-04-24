package net.honeyberries.util;

import net.dv8tion.jda.api.JDA;
import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.User;
import net.dv8tion.jda.api.events.interaction.ModalInteractionEvent;
import net.dv8tion.jda.api.events.interaction.command.SlashCommandInteractionEvent;
import net.dv8tion.jda.api.events.interaction.component.StringSelectInteractionEvent;
import net.dv8tion.jda.api.EmbedBuilder;
import net.dv8tion.jda.api.entities.User;
import net.dv8tion.jda.api.events.interaction.component.ButtonInteractionEvent;
import net.honeyberries.action.RollbackHandler;
import net.honeyberries.database.repository.AppealRepository;
import net.honeyberries.database.repository.GuildModerationActionsRepository;
import net.honeyberries.datatypes.action.ActionData;
import net.honeyberries.datatypes.action.ActionType;
import net.honeyberries.datatypes.action.AppealData;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.discord.UserID;
import net.honeyberries.preferences.PreferencesManager;
import net.honeyberries.ui.AppealEmbedUI;
import org.jetbrains.annotations.NotNull;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.awt.Color;
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

        // Create the appeal (action ID is required)
        UserID userId = UserID.fromUser(event.getUser());
        UUID appealId = appealRepository.createAppeal(action.guildId(), userId, actionId, reason);

        if (appealId == null) {
            event.reply("Failed to submit appeal. Please try again later.").setEphemeral(true).queue();
            logger.error("Failed to create appeal for user {} on action {}", userId.value(), actionId);
            return;
        }

        // Load the full AppealData from DB (with embedded ActionData)
        List<AppealData> openAppeals = appealRepository.getOpenAppeals(action.guildId());
        AppealData appeal = openAppeals.stream()
                .filter(a -> a.id().equals(appealId))
                .findFirst()
                .orElse(null);

        // Notify moderators
        Guild guild = event.getJDA().getGuildById(action.guildId().value());
        if (guild != null && appeal != null) {
            notifyModerators(event.getJDA(), guild, appeal, event.getUser());
        } else if (guild == null) {
            logger.warn("Guild {} not found for appeal notification", action.guildId().value());
        } else {
            logger.warn("Failed to load created appeal {} from database", appealId);
        }

        event.reply("Your appeal has been submitted. Appeal ID: `" + appealId + "`").setEphemeral(true).queue();
    }

    /**
     * Sends a notification to moderators in the audit log channel with Accept/Reject buttons.
     */
    private void notifyModerators(
            @NotNull JDA jda,
            @NotNull Guild guild,
            @NotNull AppealData appeal,
            @NotNull User appellant) {
        try {
            var prefs = PreferencesManager.getInstance().getOrDefaultPreferences(new GuildID(guild.getIdLong()));
            var auditLogChannel = guild.getTextChannelById(prefs.auditLogChannelId().value());

            if (auditLogChannel == null) {
                // Fallback to hardcoded channel name if no preference is set
                auditLogChannel = guild.getTextChannels().stream()
                        .filter(channel -> channel.getName().equals("audit-log"))
                        .findFirst()
                        .orElse(null);
            }

            if (auditLogChannel == null) {
                logger.warn("Audit log channel not found in guild {} for appeal notification", guild.getId());
                return;
            }

            auditLogChannel.sendMessage(AppealEmbedUI.buildAppealNotificationEmbed(appeal, appellant)).queue();
        } catch (Exception e) {
            logger.error("Failed to notify moderators of appeal {} in guild {}", appeal.id(), guild.getId(), e);
        }
    }

    /**
     * Handles Accept/Reject button interactions on appeal embeds.
     * Checks moderator permissions, then either rolls back the action or closes the appeal with a DM.
     */
    public void handleAppealButton(@NotNull ButtonInteractionEvent event) {
        Objects.requireNonNull(event, "event must not be null");

        // Permission check
        if (!DiscordUtils.isAdmin(event.getMember())) {
            event.reply("Only administrators can resolve appeals.").setEphemeral(true).queue();
            return;
        }

        String componentId = event.getComponentId();
        String[] parts = componentId.split(":");
        if (parts.length < 3) {
            event.reply("Invalid button ID.").setEphemeral(true).queue();
            return;
        }

        UUID appealId;
        try {
            appealId = UUID.fromString(parts[2]);
        } catch (IllegalArgumentException e) {
            event.reply("Invalid appeal ID.").setEphemeral(true).queue();
            logger.warn("Failed to parse appeal ID from button ID: {}", componentId);
            return;
        }

        // Load the guild from the event
        var guild = event.getGuild();
        if (guild == null) {
            event.reply("Guild not found.").setEphemeral(true).queue();
            return;
        }

        GuildID guildId = new GuildID(guild.getIdLong());

        // Find the appeal in the open appeals list
        List<AppealData> openAppeals = appealRepository.getOpenAppeals(guildId);
        AppealData appeal = openAppeals.stream()
                .filter(a -> a.id().equals(appealId))
                .findFirst()
                .orElse(null);

        if (appeal == null) {
            event.reply("This appeal has already been resolved or does not exist.").setEphemeral(true).queue();
            return;
        }

        boolean isAccept = componentId.startsWith("appeal:accept:");
        String moderatorName = event.getUser().getName();

        if (isAccept) {
            // Accept: rollback the action
            ActionData action = appeal.actionData();
            String rollbackReason = "Appeal accepted by " + moderatorName;
            boolean rollbackSuccess = RollbackHandler.getInstance().rollbackAction(action.id(), rollbackReason);

            if (!rollbackSuccess) {
                event.reply("Failed to rollback the action. Please check bot permissions.").setEphemeral(true).queue();
                return;
            }

            // Close the appeal
            String closeNote = "Accepted by " + moderatorName;
            appealRepository.closeAppeal(guildId, appealId, closeNote);

            // DM the appellant
            User appellant = event.getJDA().retrieveUserById(appeal.userId().value()).complete();
            if (appellant != null) {
                appellant.openPrivateChannel()
                        .flatMap(channel -> channel.sendMessage("✅ Your appeal has been accepted. The action has been reversed."))
                        .queue(success -> logger.info("DM sent to appellant {} for accepted appeal {}", appeal.userId().value(), appealId),
                               error -> logger.warn("Failed to DM appellant {} for accepted appeal {}", appeal.userId().value(), appealId));
            }

            // Update the embed: change to green with "Accepted" title
            updateAppealEmbedAccepted(event, appeal, moderatorName);
            event.reply("Appeal accepted.").setEphemeral(true).queue();
        } else {
            // Reject: close the appeal without rollback
            String closeNote = "Rejected by " + moderatorName;
            appealRepository.closeAppeal(guildId, appealId, closeNote);

            // DM the appellant
            User appellant = event.getJDA().retrieveUserById(appeal.userId().value()).complete();
            if (appellant != null) {
                appellant.openPrivateChannel()
                        .flatMap(channel -> channel.sendMessage("❌ Your appeal has been reviewed and rejected."))
                        .queue(success -> logger.info("DM sent to appellant {} for rejected appeal {}", appeal.userId().value(), appealId),
                               error -> logger.warn("Failed to DM appellant {} for rejected appeal {}", appeal.userId().value(), appealId));
            }

            // Update the embed: change to red with "Rejected" title
            updateAppealEmbedRejected(event, appeal, moderatorName);
            event.reply("Appeal rejected.").setEphemeral(true).queue();
        }
    }

    /**
     * Updates the appeal embed to show "Accepted" status with buttons disabled.
     */
    private void updateAppealEmbedAccepted(
            @NotNull ButtonInteractionEvent event,
            @NotNull AppealData appeal,
            @NotNull String moderatorName) {
        event.deferEdit().queue();

        EmbedBuilder embed = new EmbedBuilder()
                .setTitle("✅ Appeal Accepted")
                .setColor(Color.GREEN)
                .setTimestamp(appeal.submittedTimestamp())
                .addField("Appellant", DiscordUtils.userMention(appeal.userId()), true)
                .addField("Moderator", DiscordUtils.userMention(appeal.actionData().moderatorId()), true)
                .addField("Action Type", appeal.actionData().action().name(), true)
                .addField("Original Reason", appeal.actionData().reason(), false)
                .addField("Appeal Reason", appeal.reason(), false)
                .addField("Resolved by", DiscordUtils.userMention(new UserID(event.getUser().getIdLong())), true)
                .setFooter("Appeal ID: " + appeal.id());

        event.getHook().editOriginalEmbeds(embed.build())
                .setComponents() // Clear all components (buttons)
                .queue();
    }

    /**
     * Updates the appeal embed to show "Rejected" status with buttons disabled.
     */
    private void updateAppealEmbedRejected(
            @NotNull ButtonInteractionEvent event,
            @NotNull AppealData appeal,
            @NotNull String moderatorName) {
        event.deferEdit().queue();

        EmbedBuilder embed = new EmbedBuilder()
                .setTitle("❌ Appeal Rejected")
                .setColor(Color.RED)
                .setTimestamp(appeal.submittedTimestamp())
                .addField("Appellant", DiscordUtils.userMention(appeal.userId()), true)
                .addField("Moderator", DiscordUtils.userMention(appeal.actionData().moderatorId()), true)
                .addField("Action Type", appeal.actionData().action().name(), true)
                .addField("Original Reason", appeal.actionData().reason(), false)
                .addField("Appeal Reason", appeal.reason(), false)
                .addField("Resolved by", DiscordUtils.userMention(new UserID(event.getUser().getIdLong())), true)
                .setFooter("Appeal ID: " + appeal.id());

        event.getHook().editOriginalEmbeds(embed.build())
                .setComponents() // Clear all components (buttons)
                .queue();
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
