package net.honeyberries.discord.slashCommands;

import net.dv8tion.jda.api.EmbedBuilder;
import net.dv8tion.jda.api.entities.Guild;
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
import net.honeyberries.database.AppealRepository;
import net.honeyberries.database.GuildPreferencesRepository;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.preferences.GuildPreferences;
import org.jetbrains.annotations.NotNull;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.awt.Color;
import java.time.Instant;
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
                        new SubcommandData("submit", "Submit an appeal for a moderation action taken against you")
                                .addOption(OptionType.STRING, "reason",
                                        "Explain why you believe the action was incorrect", true),
                        new SubcommandData("list", "List open appeals (administrator only)"),
                        new SubcommandData("close", "Close/resolve an appeal (administrator only)")
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

        Guild guild = event.getGuild();
        if (guild == null) {
            reply(event, "This command can only be used inside a server.");
            return;
        }

        String subcommand = event.getSubcommandName();
        if (subcommand == null) {
            reply(event, "Please specify a subcommand.");
            return;
        }

        try {
            switch (subcommand) {
                case "submit" -> handleSubmit(event, guild);
                case "list"   -> handleList(event, guild);
                case "close"  -> handleClose(event, guild);
                default       -> reply(event, "Unknown subcommand.");
            }
        } catch (Exception e) {
            logger.error("Error handling /appeal {}", subcommand, e);
            reply(event, "An unexpected error occurred.");
        }
    }

    /**
     * Handles the {@code /appeal submit} subcommand.
     * Creates an appeal record, acknowledges the submitter ephemerally, and forwards
     * the appeal embed to the guild's audit log channel so moderators see it promptly.
     *
     * @param event the interaction event, must not be {@code null}
     * @param guild the guild in which the command was issued, must not be {@code null}
     */
    private void handleSubmit(@NotNull SlashCommandInteractionEvent event, @NotNull Guild guild) {
        Objects.requireNonNull(event, "event must not be null");
        Objects.requireNonNull(guild, "guild must not be null");

        String reason = event.getOption("reason", OptionMapping::getAsString);
        if (reason == null || reason.isBlank()) {
            reply(event, "Please provide a reason for your appeal.");
            return;
        }

        User appellant = event.getUser();
        GuildID guildId = GuildID.fromGuild(guild);

        UUID appealId = AppealRepository.getInstance().createAppeal(guildId, appellant.getIdLong(), reason);
        if (appealId == null) {
            reply(event, "Failed to submit your appeal due to a server error. Please try again later.");
            return;
        }

        reply(event, "Your appeal has been submitted (ID: `" + appealId + "`). "
                + "A moderator will review it shortly.");
        logger.info("Appeal {} submitted by user {} in guild {}", appealId, appellant.getId(), guild.getId());

        notifyModerators(guild, guildId, appellant, reason, appealId);
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

        if (!isAdmin(event)) {
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
            sb.append(String.format("• `%s` — <@%d> — %s%n",
                    a.id(), a.userId(), truncate(a.reason(), 60)));
        }
        sb.append("\nUse `/appeal close <appeal_id>` to resolve an appeal.");
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

        if (!isAdmin(event)) {
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
        boolean closed = AppealRepository.getInstance().closeAppeal(appealId, note);

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
     * @param guild     the guild, must not be {@code null}
     * @param guildId   the guild's typed ID, must not be {@code null}
     * @param appellant the user who submitted the appeal, must not be {@code null}
     * @param reason    the appeal text, must not be {@code null}
     * @param appealId  the UUID assigned to the new appeal, must not be {@code null}
     */
    private void notifyModerators(
            @NotNull Guild guild,
            @NotNull GuildID guildId,
            @NotNull User appellant,
            @NotNull String reason,
            @NotNull UUID appealId) {
        Objects.requireNonNull(guild, "guild must not be null");
        Objects.requireNonNull(guildId, "guildId must not be null");
        Objects.requireNonNull(appellant, "appellant must not be null");
        Objects.requireNonNull(reason, "reason must not be null");
        Objects.requireNonNull(appealId, "appealId must not be null");

        try {
            GuildPreferences preferences = GuildPreferencesRepository.getInstance().getGuildPreferences(guildId);
            if (preferences == null || preferences.auditLogChannelId() == null) {
                return;
            }

            Channel auditChannel = guild.getGuildChannelById(preferences.auditLogChannelId().value());
            if (!(auditChannel instanceof MessageChannel messageChannel)) {
                logger.warn("Audit channel {} is unavailable in guild {} — appeal notification skipped",
                        preferences.auditLogChannelId(), guild.getId());
                return;
            }

            EmbedBuilder embed = new EmbedBuilder()
                    .setTitle("📋 New Moderation Appeal")
                    .setColor(Color.CYAN)
                    .setTimestamp(Instant.now())
                    .addField("Appellant", "<@" + appellant.getId() + ">", true)
                    .addField("Appeal ID", "`" + appealId + "`", true)
                    .addField("Reason", reason, false)
                    .setThumbnail(appellant.getEffectiveAvatarUrl())
                    .setFooter("Use /appeal close " + appealId + " to resolve", null);

            messageChannel.sendMessageEmbeds(embed.build()).queue();
        } catch (Exception e) {
            logger.warn("Failed to notify moderators of appeal {} in guild {}", appealId, guild.getId(), e);
        }
    }

    /**
     * Checks whether the invoking member has the ADMINISTRATOR permission.
     *
     * @param event the interaction event, must not be {@code null}
     * @return {@code true} if the member is an administrator
     */
    private static boolean isAdmin(@NotNull SlashCommandInteractionEvent event) {
        var member = event.getMember();
        return member != null && member.hasPermission(net.dv8tion.jda.api.Permission.ADMINISTRATOR);
    }

    /**
     * Truncates a string to the given max length, appending {@code "…"} if shortened.
     *
     * @param text   the string to truncate, must not be {@code null}
     * @param maxLen maximum length before truncation
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
