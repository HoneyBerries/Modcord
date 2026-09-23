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
import net.honeyberries.database.repository.GuildModerationActionsRepository;
import net.honeyberries.datatypes.action.ActionData;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.discord.UserID;
import net.dv8tion.jda.api.utils.messages.MessageCreateData;
import net.honeyberries.ui.ActionEmbedUI;
import net.honeyberries.util.DiscordUtils;
import net.honeyberries.util.SlashCommandUtils;
import org.jetbrains.annotations.NotNull;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;

/**
 * Slash command handler for browsing moderation actions.
 * <p>
 * Provides three subcommands:
 * <ul>
 *   <li>{@code /action list [limit]} — List recent active moderation actions (default: 5).</li>
 *   <li>{@code /action user <user>} — List all actions for a specific user.</li>
 *   <li>{@code /action get <action_id>} — Retrieve a single action by UUID.</li>
 * </ul>
 */
public class ActionCommands extends ListenerAdapter {

    private static final Logger logger = LoggerFactory.getLogger(ActionCommands.class);
    private static final int DEFAULT_LIMIT = 5;

    /**
     * Registers {@code /action} and its subcommands with Discord.
     *
     * @param commands the command list update action to register with, must not be {@code null}
     * @throws NullPointerException if {@code commands} is {@code null}
     */
    public void registerActionCommands(@NotNull CommandListUpdateAction commands) {
        Objects.requireNonNull(commands, "commands must not be null");
        SlashCommandData actionCommand = Commands.slash("action", "Browse moderation actions")
                .addSubcommands(
                        new SubcommandData("list", "List recent active moderation actions")
                                .addOption(OptionType.INTEGER, "limit", "Number of recent actions to show (default: 5)", false),
                        new SubcommandData("user", "List all actions for a specific user")
                                .addOption(OptionType.USER, "user", "User to look up", true),
                        new SubcommandData("get", "Retrieve a specific moderation action by ID")
                                .addOption(OptionType.STRING, "action_id", "UUID of the action", true)
                );

        commands.addCommands(actionCommand);
        logger.info("Registered /action commands");
    }

    /**
     * Handles {@code /action} interactions.
     * Routes to the appropriate subcommand handler after validating guild membership and
     * that the invoking member has administrator-level permissions.
     *
     * @param event the slash command interaction event from Discord, must not be {@code null}
     * @throws NullPointerException if {@code event} is {@code null}
     */
    @Override
    public void onSlashCommandInteraction(@NotNull SlashCommandInteractionEvent event) {
        Objects.requireNonNull(event, "event must not be null");
        if (!event.getName().equals("action")) {
            return;
        }

        Guild guild = SlashCommandUtils.validateGuildContext(event, "This command can only be used in servers.");
        if (guild == null) {
            return;
        }

        Member member = event.getMember();
        if (!DiscordUtils.isAdmin(member)) {
            SlashCommandUtils.replyEphemeral(event, "Only administrators can browse moderation actions.");
            return;
        }

        String subcommand = event.getSubcommandName();
        if (subcommand == null) {
            SlashCommandUtils.replyEphemeral(event, "Please specify a subcommand.");
            return;
        }

        try {
            switch (subcommand) {
                case "list" -> handleList(event, guild);
                case "user" -> handleUser(event, guild);
                case "get"  -> handleGet(event, guild);
                default     -> SlashCommandUtils.replyEphemeral(event, "Unknown subcommand.");
            }
        } catch (Exception e) {
            logger.error("Error handling /action {}", subcommand, e);
            SlashCommandUtils.replyEphemeral(event, "An unexpected error occurred.");
        }
    }

    /**
     * Handles the {@code /action list} subcommand.
     * Displays recent active (non-reversed, non-NULL) moderation actions for this guild.
     * Uses an optional limit argument; defaults to 10 if not specified.
     * Each action is sent as a separate embed.
     *
     * @param event the interaction event, must not be {@code null}
     * @param guild the guild in which the command was issued, must not be {@code null}
     */
    private void handleList(@NotNull SlashCommandInteractionEvent event, @NotNull Guild guild) {
        Objects.requireNonNull(event, "event must not be null");
        Objects.requireNonNull(guild, "guild must not be null");

        int limit = event.getOption("limit", DEFAULT_LIMIT, OptionMapping::getAsInt);
        if (limit <= 0) {
            SlashCommandUtils.replyEphemeral(event, "Limit must be a positive number.");
            return;
        }

        GuildID guildId = GuildID.fromGuild(guild);
        List<ActionData> recentActions = GuildModerationActionsRepository.getInstance().getRecentActiveActions(guildId, limit);

        if (recentActions.isEmpty()) {
            SlashCommandUtils.replyEphemeral(event, "No recent active moderation actions found for this server.");
            return;
        }

        List<MessageCreateData> embeds = recentActions.stream()
                .map(action -> {
                    User user = event.getJDA().retrieveUserById(action.userId().value()).complete();
                    return user != null ? ActionEmbedUI.buildNotificationEmbed(action, user) : null;
                })
                .filter(Objects::nonNull)
                .toList();

        SlashCommandUtils.sendEphemeralEmbeds(event, "Recent active moderation actions:", embeds);
    }

    /**
     * Handles the {@code /action user} subcommand.
     * Displays all moderation actions for a specific user in this guild.
     * Each action is sent as a separate embed.
     *
     * @param event the interaction event, must not be {@code null}
     * @param guild the guild in which the command was issued, must not be {@code null}
     */
    private void handleUser(@NotNull SlashCommandInteractionEvent event, @NotNull Guild guild) {
        Objects.requireNonNull(event, "event must not be null");
        Objects.requireNonNull(guild, "guild must not be null");

        User targetUser = Objects.requireNonNull(event.getOption("user", OptionMapping::getAsUser));
        GuildID guildId = GuildID.fromGuild(guild);
        UserID userId = UserID.fromUser(targetUser);

        List<ActionData> userActions = GuildModerationActionsRepository.getInstance()
                .getActionsByUser(guildId, userId);

        if (userActions.isEmpty()) {
            SlashCommandUtils.replyEphemeral(event, "No actions found for that user.");
            return;
        }

        List<MessageCreateData> embeds = userActions.stream()
                .map(action -> ActionEmbedUI.buildNotificationEmbed(action, targetUser))
                .toList();

        SlashCommandUtils.sendEphemeralEmbeds(event, "Moderation actions for <@" + targetUser.getId() + ">:", embeds);
    }


    /**
     * Handles the {@code /action get} subcommand.
     * Retrieves and displays a single moderation action by its UUID.
     * Validates that the action belongs to this guild.
     *
     * @param event the interaction event, must not be {@code null}
     * @param guild the guild in which the command was issued, must not be {@code null}
     */
    private void handleGet(@NotNull SlashCommandInteractionEvent event, @NotNull Guild guild) {
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

        ActionData action = GuildModerationActionsRepository.getInstance().getActionById(actionId);
        if (action == null) {
            SlashCommandUtils.replyEphemeral(event, "Action `" + actionId + "` not found.");
            return;
        }

        GuildID guildId = GuildID.fromGuild(guild);
        if (!action.guildId().equals(guildId)) {
            SlashCommandUtils.replyEphemeral(event, "Action `" + actionId + "` does not belong to this guild.");
            return;
        }

        User user = event.getJDA().retrieveUserById(action.userId().value()).complete();
        if (user != null) {
            SlashCommandUtils.replyEphemeral(event, "");
            SlashCommandUtils.sendEphemeralFollowUp(event, ActionEmbedUI.buildNotificationEmbed(action, user));
        } else {
            SlashCommandUtils.replyEphemeral(event, "");
            event.getJDA().retrieveUserById(action.userId().value())
                .queue(resolvedUser -> SlashCommandUtils.sendEphemeralFollowUp(event, ActionEmbedUI.buildNotificationEmbed(action, resolvedUser)),
                       ex -> SlashCommandUtils.replyEphemeral(event, "Could not resolve user for action `" + actionId + "`.")
                );
        }
    }
}
