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

import java.util.UUID;

public class ModerationCommands extends ListenerAdapter {

    private static final Logger logger = LoggerFactory.getLogger(ModerationCommands.class);
    private static final String DEFAULT_REASON = "No reason provided.";
    private static final long MAX_TIMEOUT_MINUTES = 40_320; // Discord hard limit: 28 days.
    private static final long MAX_BAN_DAYS = 365;

    public void registerModerationCommands(@NotNull CommandListUpdateAction commands) {
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

    @Override
    public void onSlashCommandInteraction(@NotNull SlashCommandInteractionEvent event) {
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

    private void handleTimeout(
            @NotNull SlashCommandInteractionEvent event,
            @NotNull Guild guild,
            @NotNull Member moderator,
            @NotNull User targetUser,
            @NotNull String reason
    ) {
        Long minutes = event.getOption("minutes", OptionMapping::getAsLong);
        if (minutes == null || minutes <= 0 || minutes > MAX_TIMEOUT_MINUTES) {
            reply(event, "Timeout duration must be between 1 and 40320 minutes.");
            return;
        }

        long timeoutSeconds = minutes * 60;
        executeAction(event, guild, moderator, targetUser, ActionType.TIMEOUT, reason, timeoutSeconds, 0);
    }

    private void handleBan(
            @NotNull SlashCommandInteractionEvent event,
            @NotNull Guild guild,
            @NotNull Member moderator,
            @NotNull User targetUser,
            @NotNull String reason
    ) {
        Long days = event.getOption("days", OptionMapping::getAsLong);
        if (days == null || days <= 0 || days > MAX_BAN_DAYS) {
            reply(event, "Ban duration must be between 1 and 365 days.");
            return;
        }

        long banSeconds = days * 86_400;
        executeAction(event, guild, moderator, targetUser, ActionType.BAN, reason, 0, banSeconds);
    }

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

    private static boolean hasAnyModerationPermission(@NotNull Member member) {
        return member.hasPermission(Permission.MODERATE_MEMBERS)
                || member.hasPermission(Permission.KICK_MEMBERS)
                || member.hasPermission(Permission.BAN_MEMBERS)
                || member.hasPermission(Permission.ADMINISTRATOR);
    }

    private static void reply(@NotNull SlashCommandInteractionEvent event, @NotNull String message) {
        event.reply(message).setEphemeral(true).queue();
    }
}
