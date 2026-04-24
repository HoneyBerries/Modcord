package net.honeyberries.discord.slashCommands;

import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.User;
import net.dv8tion.jda.api.events.interaction.ModalInteractionEvent;
import net.dv8tion.jda.api.events.interaction.command.SlashCommandInteractionEvent;
import net.dv8tion.jda.api.events.interaction.component.ButtonInteractionEvent;
import net.dv8tion.jda.api.events.interaction.component.StringSelectInteractionEvent;
import net.dv8tion.jda.api.hooks.ListenerAdapter;
import net.dv8tion.jda.api.interactions.commands.OptionMapping;
import net.dv8tion.jda.api.interactions.commands.OptionType;
import net.dv8tion.jda.api.interactions.commands.build.Commands;
import net.dv8tion.jda.api.interactions.commands.build.SlashCommandData;
import net.dv8tion.jda.api.interactions.commands.build.SubcommandData;
import net.dv8tion.jda.api.requests.restaction.CommandListUpdateAction;
import net.honeyberries.database.repository.AppealRepository;
import net.honeyberries.datatypes.action.AppealData;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.ui.AppealEmbedUI;
import net.honeyberries.util.AppealCommandHelper;
import net.honeyberries.util.DiscordUtils;
import org.jetbrains.annotations.NotNull;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.List;
import java.util.Objects;
import java.util.UUID;

/**
 * Slash command handler for the ban appeal workflow.
 * <p>
 * Users who have been moderated can submit an appeal via {@code /appeal submit <reason>}.
 * Appeals are stored in the database and optionally forwarded to the guild's configured
 * audit log channel so moderators can review them.
 * <p>
 * The appeal system is deliberately lightweight: it creates a paper trail and notifies
 * moderators but does not automatically lift any moderation actions — a human moderator
 * reviews and then uses {@code /rollback action <id>} to undo the relevant action if warranted.
 * <p>
 * Subcommands:
 * <ul>
 *   <li>{@code /appeal submit <reason>} — Submit an appeal (usable by anyone in the guild).</li>
 *   <li>{@code /appeal list} — List open appeals (administrator only).</li>
 *   <li>{@code /appeal close <appeal_id>} — Mark an appeal as reviewed/closed (administrator only).</li>
 * </ul>
 */
public class AppealCommands extends ListenerAdapter {

    private static final Logger logger = LoggerFactory.getLogger(AppealCommands.class);
    private static final int DEFAULT_LIMIT = 5;
    private final AppealCommandHelper helper = new AppealCommandHelper();

    /**
     * Registers the {@code /appeal} command with Discord.
     *
     * @param commands the command list update action to register with, must not be {@code null}
     * @throws NullPointerException if {@code commands} is {@code null}
     */
    public void registerAppealCommands(@NotNull CommandListUpdateAction commands) {
        Objects.requireNonNull(commands, "commands must not be null");
        SlashCommandData appealCommand = Commands.slash("appeal", "Ban/moderation appeal system")
                .addSubcommands(
                        new SubcommandData("submit", "Submit an appeal for a moderation action (works in DMs)"),
                        new SubcommandData("list", "List open appeals (administrator only, guild only)")
                                .addOption(OptionType.INTEGER, "limit",
                                        "Number of appeals to show (default 5)", false),
                        new SubcommandData("get", "Get details of a specific appeal (administrator only, guild only)")
                                .addOption(OptionType.STRING, "appeal_id",
                                        "UUID of the appeal to view", true),
                        new SubcommandData("close", "Close/resolve an appeal (administrator only, guild only)")
                                .addOption(OptionType.STRING, "appeal_id",
                                        "UUID of the appeal to close", true)
                                .addOption(OptionType.STRING, "note",
                                        "Optional resolution note visible in the audit trail", false)
                );

        commands.addCommands(appealCommand);
        logger.info("Registered /appeal commands");
    }

    /**
     * Dispatches {@code /appeal} subcommands to their handlers.
     *
     * @param event the slash command interaction event from Discord, must not be {@code null}
     * @throws NullPointerException if {@code event} is {@code null}
     */
    @Override
    public void onSlashCommandInteraction(@NotNull SlashCommandInteractionEvent event) {
        Objects.requireNonNull(event, "event must not be null");
        if (!event.getName().equals("appeal")) {
            return;
        }

        String subcommand = event.getSubcommandName();
        if (subcommand == null) {
            reply(event, "Please specify a subcommand.");
            return;
        }

        try {
            switch (subcommand) {
                case "submit" -> handleSubmit(event);
                case "list"   -> {
                    Guild guild = event.getGuild();
                    if (guild == null) {
                        reply(event, "List can only be used inside a server.");
                        return;
                    }
                    handleList(event, guild);
                }
                case "get"    -> {
                    Guild guild = event.getGuild();
                    if (guild == null) {
                        reply(event, "Get can only be used inside a server.");
                        return;
                    }
                    handleGet(event, guild);
                }
                case "close"  -> {
                    Guild guild = event.getGuild();
                    if (guild == null) {
                        reply(event, "Close can only be used inside a server.");
                        return;
                    }
                    handleClose(event, guild);
                }
                default       -> reply(event, "Unknown subcommand.");
            }
        } catch (Exception e) {
            logger.error("Error handling /appeal {}", subcommand, e);
            reply(event, "An unexpected error occurred.");
        }
    }

    /**
     * Handles string select menu interactions from the appeal action selection.
     */
    @Override
    public void onStringSelectInteraction(@NotNull StringSelectInteractionEvent event) {
        Objects.requireNonNull(event, "event must not be null");
        if (!event.getComponentId().equals("appeal_action_select")) {
            return;
        }

        try {
            helper.handleActionSelect(event);
        } catch (Exception e) {
            logger.error("Error handling appeal action select", e);
            event.reply("An unexpected error occurred.").setEphemeral(true).queue();
        }
    }

    /**
     * Handles modal interactions from the appeal reason submission.
     */
    @Override
    public void onModalInteraction(@NotNull ModalInteractionEvent event) {
        Objects.requireNonNull(event, "event must not be null");
        if (!event.getModalId().startsWith("appeal:submit:")) {
            return;
        }

        try {
            helper.handleModalSubmit(event);
        } catch (Exception e) {
            logger.error("Error handling appeal modal submission", e);
            event.reply("An unexpected error occurred.").setEphemeral(true).queue();
        }
    }

    /**
     * Handles button interactions for appeal acceptance/rejection.
     */
    @Override
    public void onButtonInteraction(@NotNull ButtonInteractionEvent event) {
        Objects.requireNonNull(event, "event must not be null");
        String componentId = event.getComponentId();
        if (componentId.startsWith("appeal:accept:") || componentId.startsWith("appeal:reject:")) {
            try {
                helper.handleAppealButton(event);
            } catch (Exception e) {
                logger.error("Error handling appeal button interaction", e);
                event.reply("An unexpected error occurred.").setEphemeral(true).queue();
            }
        }
    }

    /**
     * Handles the {@code /appeal submit} subcommand.
     * Shows a select menu for the user to pick from their moderation history.
     *
     * @param event the interaction event, must not be {@code null}
     */
    private void handleSubmit(@NotNull SlashCommandInteractionEvent event) {
        Objects.requireNonNull(event, "event must not be null");
        helper.handleShowActionSelect(event);
    }

    /**
     * Handles the {@code /appeal list} subcommand.
     * Displays recent open (unresolved) appeals for the guild as rich embeds. Administrator only.
     * Uses an optional limit argument; defaults to 5 if not specified.
     *
     * @param event the interaction event, must not be {@code null}
     * @param guild the guild in which the command was issued, must not be {@code null}
     */
    private void handleList(@NotNull SlashCommandInteractionEvent event, @NotNull Guild guild) {
        Objects.requireNonNull(event, "event must not be null");
        Objects.requireNonNull(guild, "guild must not be null");

        if (!DiscordUtils.isAdmin(event.getMember())) {
            reply(event, "Only administrators can view appeals.");
            return;
        }

        int limit = event.getOption("limit", DEFAULT_LIMIT, OptionMapping::getAsInt);
        if (limit <= 0) {
            reply(event, "Limit must be a positive number.");
            return;
        }

        GuildID guildId = GuildID.fromGuild(guild);
        List<AppealData> openAppeals = AppealRepository.getInstance().getOpenAppeals(guildId);

        if (openAppeals.isEmpty()) {
            reply(event, "No open appeals for this server.");
            return;
        }

        // Show only up to the limit, oldest first (already ordered that way from the query)
        List<AppealData> appealsToShow = openAppeals.stream()
                .limit(limit)
                .toList();

        event.reply("Open appeals (" + appealsToShow.size() + " of " + openAppeals.size() + "):").setEphemeral(true).queue();
        for (AppealData appeal : appealsToShow) {
            User appellant = event.getJDA().retrieveUserById(appeal.userId().value()).complete();
            if (appellant != null) {
                event.getHook().sendMessage(AppealEmbedUI.buildAppealNotificationEmbed(appeal, appellant)).setEphemeral(true).queue();
            }
        }
    }

    /**
     * Handles the {@code /appeal get} subcommand.
     * Displays a single appeal by UUID as a rich embed. Administrator only.
     *
     * @param event the interaction event, must not be {@code null}
     * @param guild the guild in which the command was issued, must not be {@code null}
     */
    private void handleGet(@NotNull SlashCommandInteractionEvent event, @NotNull Guild guild) {
        Objects.requireNonNull(event, "event must not be null");
        Objects.requireNonNull(guild, "guild must not be null");

        if (!DiscordUtils.isAdmin(event.getMember())) {
            reply(event, "Only administrators can view appeals.");
            return;
        }

        String appealIdStr = event.getOption("appeal_id", OptionMapping::getAsString);
        if (appealIdStr == null || appealIdStr.isBlank()) {
            reply(event, "Please provide the appeal UUID.");
            return;
        }

        UUID appealId;
        try {
            appealId = UUID.fromString(appealIdStr.strip());
        } catch (IllegalArgumentException e) {
            reply(event, "Invalid appeal ID format. Please provide a valid UUID.");
            return;
        }

        GuildID guildId = GuildID.fromGuild(guild);
        List<AppealData> openAppeals = AppealRepository.getInstance().getOpenAppeals(guildId);
        AppealData appeal = openAppeals.stream()
                .filter(a -> a.id().equals(appealId))
                .findFirst()
                .orElse(null);

        if (appeal == null) {
            reply(event, "Appeal not found or has been resolved.");
            return;
        }

        User appellant = event.getJDA().retrieveUserById(appeal.userId().value()).complete();
        if (appellant != null) {
            event.reply(AppealEmbedUI.buildAppealNotificationEmbed(appeal, appellant)).setEphemeral(true).queue();
        } else {
            reply(event, "Could not retrieve appellant information.");
        }
    }

    /**
     * Handles the {@code /appeal close} subcommand.
     * Marks the appeal as resolved. Administrator only.
     *
     * @param event the interaction event, must not be {@code null}
     * @param guild the guild in which the command was issued, must not be {@code null}
     */
    private void handleClose(@NotNull SlashCommandInteractionEvent event, @NotNull Guild guild) {
        Objects.requireNonNull(event, "event must not be null");
        Objects.requireNonNull(guild, "guild must not be null");

        if (!DiscordUtils.isAdmin(event.getMember())) {
            reply(event, "Only administrators can close appeals.");
            return;
        }

        String appealIdStr = event.getOption("appeal_id", OptionMapping::getAsString);
        if (appealIdStr == null || appealIdStr.isBlank()) {
            reply(event, "Please provide the appeal UUID.");
            return;
        }

        UUID appealId;
        try {
            appealId = UUID.fromString(appealIdStr.strip());
        } catch (IllegalArgumentException e) {
            reply(event, "Invalid appeal ID format. Please provide a valid UUID.");
            return;
        }

        String note = event.getOption("note", "No note provided.", OptionMapping::getAsString);
        GuildID guildId = GuildID.fromGuild(guild);
        boolean closed = AppealRepository.getInstance().closeAppeal(guildId, appealId, note);

        if (closed) {
            reply(event, "Appeal `" + appealId + "` has been closed.");
            logger.info("Appeal {} closed by {} in guild {} — note: {}",
                    appealId, event.getUser().getId(), guild.getId(), note);
        } else {
            reply(event, "Could not close appeal `" + appealId + "`. It may not exist or is already resolved.");
        }
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
