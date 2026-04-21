package net.honeyberries.discord.slashCommands;

import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.Member;
import net.dv8tion.jda.api.events.interaction.command.SlashCommandInteractionEvent;
import net.dv8tion.jda.api.hooks.ListenerAdapter;
import net.dv8tion.jda.api.Permission;
import net.dv8tion.jda.api.interactions.commands.OptionMapping;
import net.dv8tion.jda.api.interactions.commands.OptionType;
import net.dv8tion.jda.api.interactions.commands.build.Commands;
import net.dv8tion.jda.api.interactions.commands.build.SlashCommandData;
import net.dv8tion.jda.api.interactions.commands.build.SubcommandData;
import net.dv8tion.jda.api.requests.restaction.CommandListUpdateAction;
import net.honeyberries.action.ActionHandler;
import net.honeyberries.database.GuildModerationActionsRepository;
import net.honeyberries.datatypes.action.ActionData;
import net.honeyberries.datatypes.discord.GuildID;
import org.jetbrains.annotations.NotNull;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.List;
import java.util.Objects;
import java.util.UUID;

/**
 * Slash command handler that lets administrators undo previously applied moderation actions.
 * <p>
 * Provides two subcommands:
 * <ul>
 *   <li>{@code /rollback action <action_id> [reason]} — reverses a specific action by its UUID.</li>
 *   <li>{@code /rollback list} — lists the most recent 10 active (non-reversed) actions.</li>
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
    private static final int RECENT_ACTION_LIMIT = 10;

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
                                .addOption(OptionType.STRING, "reason", "Reason for the rollback", false),
                        new SubcommandData("list", "List the most recent active (non-reversed) moderation actions")
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

        Guild guild = event.getGuild();
        if (guild == null) {
            reply(event, "This command can only be used in servers.");
            return;
        }

        Member member = event.getMember();
        if (member == null || !member.hasPermission(Permission.ADMINISTRATOR)) {
            reply(event, "Only administrators can roll back moderation actions.");
            return;
        }

        String subcommand = event.getSubcommandName();
        if (subcommand == null) {
            reply(event, "Please specify a subcommand.");
            return;
        }

        try {
            switch (subcommand) {
                case "action" -> handleRollbackAction(event, guild);
                case "list"   -> handleListActions(event, guild);
                default       -> reply(event, "Unknown subcommand.");
            }
        } catch (Exception e) {
            logger.error("Error handling /rollback {}", subcommand, e);
            reply(event, "An unexpected error occurred.");
        }
    }

    /**
     * Handles the {@code /rollback action} subcommand.
     * Parses the action UUID, delegates reversal to {@link ActionHandler#rollbackAction}, and reports the outcome.
     *
     * @param event the interaction event, must not be {@code null}
     * @param guild the guild in which the command was issued, must not be {@code null}
     */
    private void handleRollbackAction(@NotNull SlashCommandInteractionEvent event, @NotNull Guild guild) {
        Objects.requireNonNull(event, "event must not be null");
        Objects.requireNonNull(guild, "guild must not be null");

        String actionIdStr = event.getOption("action_id", OptionMapping::getAsString);
        if (actionIdStr == null || actionIdStr.isBlank()) {
            reply(event, "Please provide a valid action UUID.");
            return;
        }

        UUID actionId;
        try {
            actionId = UUID.fromString(actionIdStr.strip());
        } catch (IllegalArgumentException e) {
            reply(event, "Invalid action ID format. Please provide a valid UUID (e.g. `a1b2c3d4-...`).");
            return;
        }

        String reason = event.getOption("reason", DEFAULT_REASON, OptionMapping::getAsString);

        boolean success = ActionHandler.getInstance().rollbackAction(actionId, reason);
        if (success) {
            reply(event, "Successfully rolled back action `" + actionId + "`.");
            logger.info("Action {} rolled back by {} in guild {} — reason: {}",
                    actionId, event.getUser().getId(), guild.getId(), reason);
        } else {
            reply(event, "Failed to roll back action `" + actionId + "`. "
                    + "It may not exist, may have already been reversed, or the bot lacks permissions.");
        }
    }

    /**
     * Handles the {@code /rollback list} subcommand.
     * Displays the most recent active (non-reversed) moderation actions for this guild.
     *
     * @param event the interaction event, must not be {@code null}
     * @param guild the guild in which the command was issued, must not be {@code null}
     */
    private void handleListActions(@NotNull SlashCommandInteractionEvent event, @NotNull Guild guild) {
        Objects.requireNonNull(event, "event must not be null");
        Objects.requireNonNull(guild, "guild must not be null");

        GuildID guildId = GuildID.fromGuild(guild);
        List<ActionData> actions = GuildModerationActionsRepository.getInstance()
                .getActiveActions(guildId);

        if (actions.isEmpty()) {
            reply(event, "No active moderation actions found for this server.");
            return;
        }

        List<ActionData> recent = actions.stream().limit(RECENT_ACTION_LIMIT).toList();
        StringBuilder sb = new StringBuilder("**Recent active moderation actions:**\n");
        for (ActionData a : recent) {
            sb.append(String.format("• `%s` — **%s** on <@%d> — %s%n",
                    a.id(), a.action().name(), a.userId().value(), truncate(a.reason(), 60)));
        }
        sb.append("\nUse `/rollback action <action_id>` to reverse any of the above.");

        reply(event, sb.toString());
    }

    /**
     * Truncates a string to the given max length, appending {@code "…"} if shortened.
     *
     * @param text    the string to truncate, must not be {@code null}
     * @param maxLen  maximum length before truncation
     * @return the (possibly truncated) string
     */
    @NotNull
    private static String truncate(@NotNull String text, int maxLen) {
        if (text.length() <= maxLen) return text;
        return text.substring(0, maxLen - 1) + "…";
    }

    /**
     * Sends an ephemeral reply to the interaction.
     *
     * @param event   the interaction event, must not be {@code null}
     * @param message the reply text, must not be {@code null}
     */
    private static void reply(@NotNull SlashCommandInteractionEvent event, @NotNull String message) {
        Objects.requireNonNull(event, "event must not be null");
        Objects.requireNonNull(message, "message must not be null");
        event.reply(message).setEphemeral(true).queue();
    }
}
