package net.honeyberries.discord.slashCommands;

import net.dv8tion.jda.api.Permission;
import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.Member;
import net.dv8tion.jda.api.entities.User;
import net.dv8tion.jda.api.entities.channel.Channel;
import net.dv8tion.jda.api.entities.channel.middleman.MessageChannel;
import net.dv8tion.jda.api.events.interaction.command.SlashCommandInteractionEvent;
import net.dv8tion.jda.api.hooks.ListenerAdapter;
import net.dv8tion.jda.api.interactions.commands.OptionMapping;
import net.dv8tion.jda.api.interactions.commands.OptionType;
import net.dv8tion.jda.api.interactions.commands.build.Commands;
import net.dv8tion.jda.api.interactions.commands.build.SlashCommandData;
import net.dv8tion.jda.api.interactions.commands.build.SubcommandData;
import net.dv8tion.jda.api.requests.restaction.CommandListUpdateAction;
import net.honeyberries.database.repository.AppealRepository;
import net.honeyberries.database.repository.GuildModerationActionsRepository;
import net.honeyberries.database.repository.GuildPreferencesRepository;
import net.honeyberries.database.repository.SpecialUsersRepository;
import net.honeyberries.datatypes.action.ActionData;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.discord.UserID;
import net.honeyberries.datatypes.preferences.GuildPreferences;
import net.honeyberries.discord.JDAManager;
import net.honeyberries.ui.AppealEmbedUI;
import net.honeyberries.util.DiscordUtils;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

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
                        new SubcommandData("submit", "Submit an appeal for a moderation action (works in DMs)")
                                .addOption(OptionType.STRING, "reason",
                                        "Explain why you believe the action was incorrect", true)
                                .addOption(OptionType.STRING, "action_id",
                                        "UUID of the moderation action (required in DM, optional in guild)", false),
                        new SubcommandData("list", "List open appeals (administrator only, guild only)"),
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
     * Handles the {@code /appeal submit} subcommand.
     * Works in both guild and DM contexts.
     * In DMs: requires action_id UUID.
     * In guilds: action_id is optional (defaults to null if not provided).
     * Creates an appeal record and notifies moderators in the target guild.
     *
     * @param event the interaction event, must not be {@code null}
     */
    private void handleSubmit(@NotNull SlashCommandInteractionEvent event) {
        Objects.requireNonNull(event, "event must not be null");

        String reason = event.getOption("reason", OptionMapping::getAsString);
        if (reason == null || reason.isBlank()) {
            reply(event, "Please provide a reason for your appeal.");
            return;
        }

        String actionIdStr = event.getOption("action_id", OptionMapping::getAsString);
        UUID actionId = null;
        GuildID guildId;

        Guild guild = event.getGuild();

        if (guild == null) {
            if (actionIdStr == null || actionIdStr.isBlank()) {
                reply(event, "In DMs, you must provide the action UUID.");
                return;
            }
            try {
                actionId = UUID.fromString(actionIdStr.strip());
            } catch (IllegalArgumentException e) {
                reply(event, "Invalid action UUID format. Please provide a valid UUID.");
                return;
            }
            ActionData action = GuildModerationActionsRepository.getInstance().getActionById(actionId);
            if (action == null) {
                reply(event, "Could not find the specified action. Please verify the UUID and try again.");
                return;
            }
            guildId = action.guildId();
        } else {
            guildId = GuildID.fromGuild(guild);
            if (actionIdStr != null && !actionIdStr.isBlank()) {
                try {
                    actionId = UUID.fromString(actionIdStr.strip());
                    ActionData action = GuildModerationActionsRepository.getInstance().getActionById(actionId);
                    if (action == null) {
                        reply(event, "Could not find the specified action. Please verify the UUID and try again.");
                        return;
                    }
                    if (!action.guildId().equals(guildId)) {
                        reply(event, "The specified action belongs to a different guild.");
                        return;
                    }
                } catch (IllegalArgumentException e) {
                    reply(event, "Invalid action UUID format. Please provide a valid UUID.");
                    return;
                }
            }
        }

        User appellant = event.getUser();
        UUID appealId = AppealRepository.getInstance().createAppeal(guildId, appellant.getIdLong(), actionId, reason);
        if (appealId == null) {
            reply(event, "Failed to submit your appeal due to a server error. Please try again later.");
            return;
        }

        reply(event, "Your appeal has been submitted (ID: `" + appealId + "`). "
                + "A moderator will review it shortly.");
        logger.info("Appeal {} submitted by user {} for action {}", appealId, appellant.getId(), actionId);

        notifyModerators(guildId, appellant, reason, appealId, actionId);
    }

    /**
     * Handles the {@code /appeal list} subcommand.
     * Displays open (unresolved) appeals for the guild. Administrator only.
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

        GuildID guildId = GuildID.fromGuild(guild);
        var openAppeals = AppealRepository.getInstance().getOpenAppeals(guildId);

        if (openAppeals.isEmpty()) {
            reply(event, "No open appeals for this server.");
            return;
        }

        StringBuilder sb = new StringBuilder("**Open appeals:**\n");
        for (var a : openAppeals) {
            String actionInfo = a.actionId() != null ? String.format(" (action: `%s`)", a.actionId()) : "";
            sb.append(String.format("• `%s` — %s — %s%s%n",
                    a.id(), DiscordUtils.userMention(a.userId()), DiscordUtils.truncate(a.reason(), 60), actionInfo));
        }
        sb.append("\nUse `/appeal close <appeal_id> [note]` to resolve an appeal.");
        reply(event, sb.toString());
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
     * Posts an embed to the guild's audit log channel so moderators are notified of the new appeal.
     * Silently skips if no audit channel is configured or if the channel is unavailable.
     *
     * @param guildId   the guild's typed ID, must not be {@code null}
     * @param appellant the user who submitted the appeal, must not be {@code null}
     * @param reason    the appeal text, must not be {@code null}
     * @param appealId  the UUID assigned to the new appeal, must not be {@code null}
     * @param actionId  the UUID of the action being appealed, may be {@code null}
     */
    private void notifyModerators(
            @NotNull GuildID guildId,
            @NotNull User appellant,
            @NotNull String reason,
            @NotNull UUID appealId,
            @Nullable UUID actionId) {
        Objects.requireNonNull(guildId, "guildId must not be null");
        Objects.requireNonNull(appellant, "appellant must not be null");
        Objects.requireNonNull(reason, "reason must not be null");
        Objects.requireNonNull(appealId, "appealId must not be null");

        try {
            GuildPreferences preferences = GuildPreferencesRepository.getInstance().getGuildPreferences(guildId);
            if (preferences == null || preferences.auditLogChannelId() == null) {
                return;
            }

            Guild guild = JDAManager.getInstance().getJDA().getGuildById(guildId.value());
            if (guild == null) {
                logger.warn("Guild {} is not accessible — appeal notification skipped", guildId);
                return;
            }

            Channel auditChannel = guild.getGuildChannelById(preferences.auditLogChannelId().value());
            if (!(auditChannel instanceof MessageChannel messageChannel)) {
                logger.warn("Audit channel {} is unavailable in guild {} — appeal notification skipped",
                        preferences.auditLogChannelId(), guildId);
                return;
            }

            messageChannel.sendMessageEmbeds(
                    AppealEmbedUI.buildAppealNotificationEmbed(appellant, appealId, actionId, reason).build()
            ).queue();
        } catch (Exception e) {
            logger.warn("Failed to notify moderators of appeal {}", appealId, e);
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
