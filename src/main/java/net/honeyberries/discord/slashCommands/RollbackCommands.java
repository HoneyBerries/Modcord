package net.honeyberries.discord.slashCommands;

import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.Member;
import net.dv8tion.jda.api.entities.User;
import net.dv8tion.jda.api.events.interaction.command.SlashCommandInteractionEvent;
import net.dv8tion.jda.api.hooks.ListenerAdapter;
import net.dv8tion.jda.api.interactions.commands.OptionMapping;
import net.dv8tion.jda.api.interactions.commands.OptionType;
import net.dv8tion.jda.api.interactions.commands.build.Commands;
import net.dv8tion.jda.api.interactions.commands.build.SlashCommandData;
import net.dv8tion.jda.api.interactions.commands.build.SubcommandData;
import net.dv8tion.jda.api.requests.restaction.CommandListUpdateAction;
import net.dv8tion.jda.api.utils.messages.MessageCreateData;
import net.honeyberries.action.RollbackHandler;
import net.honeyberries.database.repository.GuildModerationActionsRepository;
import net.honeyberries.datatypes.action.ActionData;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.services.NotificationService;
import net.honeyberries.ui.RollbackEmbedUI;
import net.honeyberries.util.DiscordUtils;
import net.honeyberries.util.SlashCommandUtils;
import org.jetbrains.annotations.NotNull;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.Objects;
import java.util.Optional;
import java.util.UUID;

/**
 * Slash command handler that lets administrators undo previously applied moderation actions.
 * <p>
 * Provides one subcommand:
 * <ul>
 *   <li>{@code /rollback action <action_id> [reason]} — reverses a specific action by its UUID.</li>
 * </ul>
 * Reversal behaviour per action type:
 * <ul>
 *   <li>BAN → unban the user</li>
 *   <li>TIMEOUT → remove the timeout</li>
 *   <li>KICK / WARN / DELETE / NULL → marked as reversed in the audit trail; no Discord action taken</li>
 * </ul>
 */
public class RollbackCommands extends ListenerAdapter {

    private static final Logger logger = LoggerFactory.getLogger(RollbackCommands.class);
    private static final String DEFAULT_REASON = "No reason provided.";

    /**
     * Registers {@code /rollback} and its subcommands with Discord.
     *
     * @param commands the command list update action to register with, must not be {@code null}
     * @throws NullPointerException if {@code commands} is {@code null}
     */
    public void registerRollbackCommands(@NotNull CommandListUpdateAction commands) {
        Objects.requireNonNull(commands, "commands must not be null");
        SlashCommandData rollbackCommand = Commands.slash("rollback", "Undo a previously applied moderation action")
                .addSubcommands(
                        new SubcommandData("action", "Reverse a specific moderation action by its ID")
                                .addOption(OptionType.STRING, "action_id", "UUID of the action to roll back", true)
                                .addOption(OptionType.STRING, "reason", "Reason for the rollback", false)
                );

        commands.addCommands(rollbackCommand);
        logger.info("Registered /rollback commands");
    }

    /**
     * Handles {@code /rollback} interactions.
     * Routes to the appropriate subcommand handler after validating guild membership and
     * that the invoking member has administrator-level permissions.
     *
     * @param event the slash command interaction event from Discord, must not be {@code null}
     * @throws NullPointerException if {@code event} is {@code null}
     */
    @Override
    public void onSlashCommandInteraction(@NotNull SlashCommandInteractionEvent event) {
        Objects.requireNonNull(event, "event must not be null");
        if (!event.getName().equals("rollback")) {
            return;
        }

        Guild guild = SlashCommandUtils.validateGuildContext(event, "This command can only be used in servers.");
        if (guild == null) {
            return;
        }

        Member member = event.getMember();
        if (!DiscordUtils.isAdmin(member)) {
            SlashCommandUtils.replyEphemeral(event, "Only administrators can roll back moderation actions.");
            return;
        }

        String subcommand = event.getSubcommandName();
        if (subcommand == null) {
            SlashCommandUtils.replyEphemeral(event, "Please specify a subcommand.");
            return;
        }

        try {
            switch (subcommand) {
                case "action" -> handleRollbackAction(event, guild);
                default       -> SlashCommandUtils.replyEphemeral(event, "Unknown subcommand.");
            }
        } catch (Exception e) {
            logger.error("Error handling /rollback {}", subcommand, e);
            SlashCommandUtils.replyEphemeral(event, "An unexpected error occurred.");
        }
    }

    /**
     * Handles the {@code /rollback action} subcommand.
     * Parses the action UUID, delegates reversal to {@link RollbackHandler#rollbackAction}, and reports the outcome.
     *
     * @param event the interaction event, must not be {@code null}
     * @param guild the guild in which the command was issued, must not be {@code null}
     */
    private void handleRollbackAction(@NotNull SlashCommandInteractionEvent event, @NotNull Guild guild) {
        Objects.requireNonNull(event, "event must not be null");
        Objects.requireNonNull(guild, "guild must not be null");

        String actionIdStr = event.getOption("action_id", OptionMapping::getAsString);
        Optional<UUID> parsedActionId = SlashCommandUtils.parseUuidOrReplyError(
                event,
                actionIdStr,
                "Please provide a valid action UUID.",
                "Invalid action ID format. Please provide a valid UUID (e.g. `a1b2c3d4-...`)."
        );
        if (parsedActionId.isEmpty()) {
            return;
        }
        UUID actionId = parsedActionId.get();

        String reason = event.getOption("reason", DEFAULT_REASON, OptionMapping::getAsString);

        // Fetch the action before rollback to use for the embed
        ActionData action = GuildModerationActionsRepository.getInstance().getActionById(actionId);
        if (action == null) {
            SlashCommandUtils.replyEphemeral(event, "Action `" + actionId + "` not found in the database.");
            return;
        }

        if (!action.guildId().equals(GuildID.fromGuild(guild))) {
            SlashCommandUtils.replyEphemeral(event, "Action `" + actionId + "` does not belong to this guild.");
            return;
        }

        boolean success = RollbackHandler.getInstance().rollbackAction(actionId, reason);
        if (success) {
            try {
                User target = event.getJDA().retrieveUserById(action.userId().value()).complete();
                if (target == null) {
                    logger.warn("Could not retrieve target user {} for rollback notifications", action.userId().value());
                    SlashCommandUtils.replyEphemeral(event, "✅ Successfully rolled back action `" + actionId + "`.");
                    return;
                }

                MessageCreateData embed = RollbackEmbedUI.buildRollbackEmbed(action, target, event.getUser(), reason);
                NotificationService.getInstance().sendDm(action.userId(), embed);
                NotificationService.getInstance().postToAuditChannel(guild, embed);

                SlashCommandUtils.replyEphemeral(event, "✅ Successfully rolled back action `" + actionId + "`.");
                logger.info("Action {} rolled back by {} in guild {} — reason: {}",
                        actionId, event.getUser().getId(), guild.getId(), reason);
            } catch (Exception e) {
                logger.error("Error sending rollback notifications for action {}", actionId, e);
                SlashCommandUtils.replyEphemeral(event, "✅ Successfully rolled back action `" + actionId + "`.");
            }
        } else {
            SlashCommandUtils.replyEphemeral(event, "Failed to roll back action `" + actionId + "`. "
                    + "It may not exist, may have already been reversed, or the bot lacks permissions.");
        }
    }
}
