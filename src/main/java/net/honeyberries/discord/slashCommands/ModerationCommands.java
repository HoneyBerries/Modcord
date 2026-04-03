package net.honeyberries.discord.slashCommands;

import net.dv8tion.jda.api.Permission;
import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.Member;
import net.dv8tion.jda.api.entities.User;
import net.dv8tion.jda.api.events.interaction.command.SlashCommandInteractionEvent;
import net.dv8tion.jda.api.hooks.ListenerAdapter;
import net.dv8tion.jda.api.interactions.commands.DefaultMemberPermissions;
import net.dv8tion.jda.api.interactions.commands.OptionMapping;
import net.dv8tion.jda.api.interactions.commands.OptionType;
import net.dv8tion.jda.api.interactions.commands.build.Commands;
import net.dv8tion.jda.api.interactions.commands.build.OptionData;
import net.dv8tion.jda.api.interactions.commands.build.SlashCommandData;
import net.dv8tion.jda.api.interactions.commands.build.SubcommandData;
import net.dv8tion.jda.api.requests.restaction.CommandListUpdateAction;
import net.honeyberries.action.ActionHandler;
import net.honeyberries.datatypes.action.ActionData;
import net.honeyberries.datatypes.action.ActionType;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.discord.UserID;
import net.honeyberries.database.GuildModerationActionsRepository;
import org.jetbrains.annotations.NotNull;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.Objects;
import java.util.UUID;

/**
 * Slash command handler for manual moderation actions.
 *
 * <p>Provides moderators with tools to take action against users including warnings, 
 * timeouts, kicks, bans, and unbans. Each action is logged to the database for audit 
 * trails and passed to the action handler for execution. This suite centralizes moderation 
 * enforcement and helps maintain server discipline and safety.
 */
public class ModerationCommands extends ListenerAdapter {

    private static final Logger logger = LoggerFactory.getLogger(ModerationCommands.class);
    private static final String DEFAULT_REASON = "No reason provided.";
    private static final long MAX_TIMEOUT_MINUTES = 40_320; // Discord hard limit: 28 days.
    private static final long MAX_BAN_DAYS = 365;

    /**
     * Registers the moderation command and its subcommands with the Discord bot.
     *
     * @param commands the command list update action to register commands with. Must not be null.
     * @throws NullPointerException if commands is null
     */
    public void registerModerationCommands(@NotNull CommandListUpdateAction commands) {
        Objects.requireNonNull(commands, "commands must not be null");
        SlashCommandData modCommand = Commands.slash("mod", "Manual moderation commands")
                .addSubcommands(
                        new SubcommandData("warn", "Warn a user")
                                .addOptions(
                                        new OptionData(OptionType.USER, "user", "User to warn", true),
                                        new OptionData(OptionType.STRING, "reason", "Reason for the warning", false)
                                ),
                        new SubcommandData("timeout", "Timeout a user")
                                .addOptions(
                                        new OptionData(OptionType.USER, "user", "User to timeout", true),
                                        new OptionData(OptionType.INTEGER, "minutes", "Timeout duration in minutes (1-40320)", true),
                                        new OptionData(OptionType.STRING, "reason", "Reason for the timeout", false)
                                ),
                        new SubcommandData("kick", "Kick a user")
                                .addOptions(
                                        new OptionData(OptionType.USER, "user", "User to kick", true),
                                        new OptionData(OptionType.STRING, "reason", "Reason for the kick", false)
                                ),
                        new SubcommandData("ban", "Ban a user")
                                .addOptions(
                                        new OptionData(OptionType.USER, "user", "User to ban", true),
                                        new OptionData(OptionType.INTEGER, "days", "Ban duration in days (1-365)", true),
                                        new OptionData(OptionType.STRING, "reason", "Reason for the ban", false)
                                ),
                        new SubcommandData("unban", "Unban a user")
                                .addOptions(
                                        new OptionData(OptionType.USER, "user", "User to unban", true),
                                        new OptionData(OptionType.STRING, "reason", "Reason for the unban", false)
                                )
                )
                .setDefaultPermissions(DefaultMemberPermissions.enabledFor(
                        Permission.MODERATE_MEMBERS,
                        Permission.KICK_MEMBERS,
                        Permission.BAN_MEMBERS
                ));

        commands.addCommands(modCommand);
        logger.info("Registered /mod commands");
    }

    /**
     * Handles slash command interactions for the moderation command.
     *
     * <p>Routes to the appropriate subcommand handler (warn, timeout, kick, ban, unban) 
     * after validating that the event is from a guild, the user has moderation permissions, 
     * and a valid target user and subcommand are specified. All actions are logged and 
     * persisted to the database.
     *
     * @param event the slash command interaction event. Must not be null.
     * @throws NullPointerException if event is null
     */
    @Override
    public void onSlashCommandInteraction(@NotNull SlashCommandInteractionEvent event) {
        Objects.requireNonNull(event, "event must not be null");
        if (!event.getName().equals("mod")) {
            return;
        }

        Guild guild = event.getGuild();
        if (guild == null) {
            reply(event, "This command can only be used in servers!");
            return;
        }

        Member moderator = event.getMember();
        if (moderator == null || !hasAnyModerationPermission(moderator)) {
            reply(event, "You need moderation permissions to use this command.");
            return;
        }

        String subcommand = event.getSubcommandName();
        if (subcommand == null) {
            reply(event, "Please specify a moderation action.");
            return;
        }

        User targetUser = event.getOption("user", OptionMapping::getAsUser);
        if (targetUser == null) {
            reply(event, "Please provide a valid user.");
            return;
        }

        String reason = event.getOption("reason", DEFAULT_REASON, OptionMapping::getAsString);

        try {
            switch (subcommand) {
                case "warn" -> executeAction(event, guild, moderator, targetUser, ActionType.WARN, reason, 0, 0);
                case "timeout" -> handleTimeout(event, guild, moderator, targetUser, reason);
                case "kick" -> executeAction(event, guild, moderator, targetUser, ActionType.KICK, reason, 0, 0);
                case "ban" -> handleBan(event, guild, moderator, targetUser, reason);
                case "unban" -> executeAction(event, guild, moderator, targetUser, ActionType.UNBAN, reason, 0, 0);
                default -> reply(event, "Unknown moderation action.");
            }
        } catch (Exception e) {
            logger.error("Error handling /mod {}", subcommand, e);
            reply(event, "An unexpected error occurred while processing the command.");
        }
    }

    /**
     * Handles the timeout subcommand.
     *
     * <p>Validates the timeout duration is within Discord's limits (1-40320 minutes) 
     * and converts it to seconds for action processing. Replies with error if duration 
     * is invalid.
     *
     * @param event the slash command interaction event. Must not be null.
     * @param guild the guild where the action is occurring. Must not be null.
     * @param moderator the member performing the action. Must not be null.
     * @param targetUser the user being timed out. Must not be null.
     * @param reason the reason for the timeout. Must not be null.
     * @throws NullPointerException if any parameter is null
     */
    private void handleTimeout(
            @NotNull SlashCommandInteractionEvent event,
            @NotNull Guild guild,
            @NotNull Member moderator,
            @NotNull User targetUser,
            @NotNull String reason
    ) {
        Objects.requireNonNull(event, "event must not be null");
        Objects.requireNonNull(guild, "guild must not be null");
        Objects.requireNonNull(moderator, "moderator must not be null");
        Objects.requireNonNull(targetUser, "targetUser must not be null");
        Objects.requireNonNull(reason, "reason must not be null");
        Long minutes = event.getOption("minutes", OptionMapping::getAsLong);
        if (minutes == null || minutes <= 0 || minutes > MAX_TIMEOUT_MINUTES) {
            reply(event, "Timeout duration must be between 1 and 40320 minutes.");
            return;
        }

        long timeoutSeconds = minutes * 60;
        executeAction(event, guild, moderator, targetUser, ActionType.TIMEOUT, reason, timeoutSeconds, 0);
    }

    /**
     * Handles the ban subcommand.
     *
     * <p>Validates the ban duration is within Discord's limits (1-365 days) and converts 
     * it to seconds for action processing. Replies with error if duration is invalid.
     *
     * @param event the slash command interaction event. Must not be null.
     * @param guild the guild where the action is occurring. Must not be null.
     * @param moderator the member performing the action. Must not be null.
     * @param targetUser the user being banned. Must not be null.
     * @param reason the reason for the ban. Must not be null.
     * @throws NullPointerException if any parameter is null
     */
    private void handleBan(
            @NotNull SlashCommandInteractionEvent event,
            @NotNull Guild guild,
            @NotNull Member moderator,
            @NotNull User targetUser,
            @NotNull String reason
    ) {
        Objects.requireNonNull(event, "event must not be null");
        Objects.requireNonNull(guild, "guild must not be null");
        Objects.requireNonNull(moderator, "moderator must not be null");
        Objects.requireNonNull(targetUser, "targetUser must not be null");
        Objects.requireNonNull(reason, "reason must not be null");
        Long days = event.getOption("days", OptionMapping::getAsLong);
        if (days == null || days <= 0 || days > MAX_BAN_DAYS) {
            reply(event, "Ban duration must be between 1 and 365 days.");
            return;
        }

        long banSeconds = days * 86_400;
        executeAction(event, guild, moderator, targetUser, ActionType.BAN, reason, 0, banSeconds);
    }

    /**
     * Executes a moderation action by creating an ActionData record and applying it.
     *
     * <p>Persists the action to the database for audit trails, then passes it to the 
     * ActionHandler for actual enforcement. Sends an ephemeral reply to the moderator 
     * indicating success or failure.
     *
     * @param event the slash command interaction event. Must not be null.
     * @param guild the guild where the action occurs. Must not be null.
     * @param moderator the member executing the action. Must not be null.
     * @param targetUser the user being acted upon. Must not be null.
     * @param actionType the type of moderation action. Must not be null.
     * @param reason the reason for the action. Must not be null.
     * @param timeoutDuration timeout duration in seconds, or 0 if not applicable
     * @param banDuration ban duration in seconds, or 0 if not applicable
     * @throws NullPointerException if any non-primitive parameter is null
     */
    private void executeAction(
            @NotNull SlashCommandInteractionEvent event,
            @NotNull Guild guild,
            @NotNull Member moderator,
            @NotNull User targetUser,
            @NotNull ActionType actionType,
            @NotNull String reason,
            long timeoutDuration,
            long banDuration
    ) {
        Objects.requireNonNull(event, "event must not be null");
        Objects.requireNonNull(guild, "guild must not be null");
        Objects.requireNonNull(moderator, "moderator must not be null");
        Objects.requireNonNull(targetUser, "targetUser must not be null");
        Objects.requireNonNull(actionType, "actionType must not be null");
        Objects.requireNonNull(reason, "reason must not be null");
        ActionData actionData = new ActionData(
                UUID.randomUUID(),
                GuildID.fromGuild(guild),
                UserID.fromUser(targetUser),
                new UserID(moderator.getIdLong()),
                actionType,
                reason,
                timeoutDuration,
                banDuration
        );

        boolean persisted = GuildModerationActionsRepository.getInstance().addActionToDatabase(actionData);
        if (!persisted) {
            logger.warn("Failed to persist manual moderation action {} for user {} in guild {}",
                    actionType, targetUser.getIdLong(), guild.getIdLong());
        }

        boolean applied = ActionHandler.getInstance().processAction(actionData);
        if (!applied) {
            reply(event, "Failed to apply " + actionType.name().toLowerCase() + " for " + targetUser.getAsMention() + ".");
            return;
        }

        reply(event, "Applied **" + actionType.name().toLowerCase() + "** to " + targetUser.getAsMention() + ".");
    }

    /**
     * Checks whether a member has any of the required moderation permissions.
     *
     * @param member the member to check. Must not be null.
     * @return true if the member has MODERATE_MEMBERS, KICK_MEMBERS, BAN_MEMBERS, or ADMINISTRATOR permission
     * @throws NullPointerException if member is null
     */
    private static boolean hasAnyModerationPermission(@NotNull Member member) {
        Objects.requireNonNull(member, "member must not be null");
        return member.hasPermission(Permission.MODERATE_MEMBERS)
                || member.hasPermission(Permission.KICK_MEMBERS)
                || member.hasPermission(Permission.BAN_MEMBERS)
                || member.hasPermission(Permission.ADMINISTRATOR);
    }

    /**
     * Sends an ephemeral reply to a slash command interaction.
     *
     * <p>All user-facing replies from moderation commands go through here to ensure 
     * consistent behavior and avoid repeating {@code setEphemeral(true)}.
     *
     * @param event the slash command interaction event. Must not be null.
     * @param message the message to send. Must not be null.
     * @throws NullPointerException if event or message is null
     */
    private static void reply(@NotNull SlashCommandInteractionEvent event, @NotNull String message) {
        Objects.requireNonNull(event, "event must not be null");
        Objects.requireNonNull(message, "message must not be null");
        event.reply(message).setEphemeral(true).queue();
    }
}
