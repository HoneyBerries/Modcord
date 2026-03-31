package net.honeyberries.discord.slashCommands;

import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.Role;
import net.dv8tion.jda.api.entities.User;
import net.dv8tion.jda.api.events.interaction.command.SlashCommandInteractionEvent;
import net.dv8tion.jda.api.hooks.ListenerAdapter;
import net.dv8tion.jda.api.interactions.commands.OptionType;
import net.dv8tion.jda.api.interactions.commands.build.Commands;
import net.dv8tion.jda.api.interactions.commands.build.OptionData;
import net.dv8tion.jda.api.interactions.commands.build.SlashCommandData;
import net.dv8tion.jda.api.interactions.commands.build.SubcommandData;
import net.dv8tion.jda.api.requests.restaction.CommandListUpdateAction;
import net.honeyberries.database.ExcludedUsersRepository;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.discord.RoleID;
import net.honeyberries.datatypes.discord.UserID;
import org.jetbrains.annotations.NotNull;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Slash command handler for managing moderation exclusions.
 */
public class ExcludeCommand extends ListenerAdapter {

    private static final Logger logger = LoggerFactory.getLogger(ExcludeCommand.class);
    private final ExcludedUsersRepository excludedUsersRepository = ExcludedUsersRepository.getInstance();

    public void registerExcludeCommands(@NotNull CommandListUpdateAction commands) {
        SubcommandData addSubcommand = new SubcommandData("add", "Exclude a user or role from moderation")
                .addOptions(
                        new OptionData(OptionType.USER, "user", "User to exclude", false),
                        new OptionData(OptionType.ROLE, "role", "Role to exclude", false)
                );

        SubcommandData removeSubcommand = new SubcommandData("remove", "Remove a user or role exclusion")
                .addOptions(
                        new OptionData(OptionType.USER, "user", "User to unexclude", false),
                        new OptionData(OptionType.ROLE, "role", "Role to unexclude", false)
                );

        SlashCommandData excludeCommand = Commands.slash("exclude", "Manage moderation exclusions")
                .addSubcommands(addSubcommand, removeSubcommand);

        commands.addCommands(excludeCommand);
        logger.info("Registered /exclude with subcommands: add, remove");
    }

    @Override
    public void onSlashCommandInteraction(@NotNull SlashCommandInteractionEvent event) {
        if (!event.getName().equals("exclude")) {
            return;
        }

        if (!event.isFromGuild()) {
            event.reply("This command can only be used in servers!").setEphemeral(true).queue();
            return;
        }

        if (!canPerformExcludeAction(event)) {
            event.reply("You are not allowed to use this command.").setEphemeral(true).queue();
            return;
        }

        String subcommand = event.getSubcommandName();
        if (subcommand == null) {
            event.reply("Please specify a subcommand.").setEphemeral(true).queue();
            return;
        }

        try {
            switch (subcommand) {
                case "add" -> handleAdd(event);
                case "remove" -> handleRemove(event);
                default -> event.reply("Unknown subcommand").setEphemeral(true).queue();
            }
        } catch (Exception e) {
            logger.error("Failed processing /exclude {}", subcommand, e);
            event.reply("Failed to process exclusion command.").setEphemeral(true).queue();
        }
    }

    private void handleAdd(@NotNull SlashCommandInteractionEvent event) {
        Guild guild = event.getGuild();
        if (guild == null) {
            event.reply("This command can only be used in servers!").setEphemeral(true).queue();
            return;
        }

        GuildID guildID = new GuildID(guild.getIdLong());
        User user = event.getOption("user", null, option -> option.getAsUser());
        Role role = event.getOption("role", null, option -> option.getAsRole());

        if (user == null && role == null) {
            event.reply("Provide either a user or a role.").setEphemeral(true).queue();
            return;
        }

        // User-level exclusions take priority when both options are provided.
        if (user != null) {
            boolean success = excludedUsersRepository.markExcluded(guildID, UserID.fromUser(user));
            if (success) {
                String message = role != null
                        ? "Excluded user " + user.getAsMention() + ". User priority applied over role option."
                        : "Excluded user " + user.getAsMention() + ".";
                event.reply(message).setEphemeral(true).queue();
            } else {
                event.reply("Failed to exclude user.").setEphemeral(true).queue();
            }
            return;
        }

        boolean success = excludedUsersRepository.markExcluded(guildID, RoleID.fromRole(role));
        if (success) {
            event.reply("Excluded role " + role.getAsMention() + ".").setEphemeral(true).queue();
        } else {
            event.reply("Failed to exclude role.").setEphemeral(true).queue();
        }
    }

    private void handleRemove(@NotNull SlashCommandInteractionEvent event) {
        Guild guild = event.getGuild();
        if (guild == null) {
            event.reply("This command can only be used in servers!").setEphemeral(true).queue();
            return;
        }

        GuildID guildID = new GuildID(guild.getIdLong());
        User user = event.getOption("user", null, option -> option.getAsUser());
        Role role = event.getOption("role", null, option -> option.getAsRole());

        if (user == null && role == null) {
            event.reply("Provide either a user or a role.").setEphemeral(true).queue();
            return;
        }

        // User-level exclusions take priority when both options are provided.
        if (user != null) {
            boolean success = excludedUsersRepository.unmarkExcluded(guildID, UserID.fromUser(user));
            if (success) {
                String message = role != null
                        ? "Removed exclusion for user " + user.getAsMention() + ". User priority applied over role option."
                        : "Removed exclusion for user " + user.getAsMention() + ".";
                event.reply(message).setEphemeral(true).queue();
            } else {
                event.reply("Failed to remove user exclusion.").setEphemeral(true).queue();
            }
            return;
        }

        boolean success = excludedUsersRepository.unmarkExcluded(guildID, RoleID.fromRole(role));
        if (success) {
            event.reply("Removed exclusion for role " + role.getAsMention() + ".").setEphemeral(true).queue();
        } else {
            event.reply("Failed to remove role exclusion.").setEphemeral(true).queue();
        }
    }

    private boolean canPerformExcludeAction(@NotNull SlashCommandInteractionEvent event) {
        // TODO: Add real permission checks for exclusion management.
        return true;
    }
}
