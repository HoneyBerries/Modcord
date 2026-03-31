package net.honeyberries.discord.slashCommands;

import net.dv8tion.jda.api.Permission;
import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.Member;
import net.dv8tion.jda.api.entities.Role;
import net.dv8tion.jda.api.entities.User;
import net.dv8tion.jda.api.events.interaction.command.SlashCommandInteractionEvent;
import net.dv8tion.jda.api.hooks.ListenerAdapter;
import net.dv8tion.jda.api.interactions.commands.OptionMapping;
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
 *
 * <p>Requires the invoking member to have {@link Permission#MANAGE_SERVER}.
 */
public class ExcludeCommand extends ListenerAdapter {

    private static final Logger logger = LoggerFactory.getLogger(ExcludeCommand.class);
    private final ExcludedUsersRepository repository = ExcludedUsersRepository.getInstance();

    public void registerExcludeCommands(@NotNull CommandListUpdateAction commands) {
        OptionData userOption = new OptionData(OptionType.USER, "user", "Target user", false);
        OptionData roleOption = new OptionData(OptionType.ROLE, "role", "Target role", false);

        SlashCommandData excludeCommand = Commands.slash("exclude", "Manage moderation exclusions")
                .addSubcommands(
                        new SubcommandData("add", "Exclude a user or role from moderation")
                                .addOptions(userOption, roleOption),
                        new SubcommandData("remove", "Remove a user or role exclusion")
                                .addOptions(userOption, roleOption)
                );

        commands.addCommands(excludeCommand);
        logger.info("Registered /exclude command");
    }

    @Override
    public void onSlashCommandInteraction(@NotNull SlashCommandInteractionEvent event) {
        if (!event.getName().equals("exclude")) return;

        Guild guild = event.getGuild();
        if (guild == null) {
            reply(event, "This command can only be used in servers!");
            return;
        }

        Member member = event.getMember();
        if (member == null || !member.hasPermission(Permission.MANAGE_SERVER)) {
            reply(event, "You need the **Manage Server** permission to use this command.");
            return;
        }

        String subcommand = event.getSubcommandName();
        if (subcommand == null) {
            reply(event, "Please specify a subcommand.");
            return;
        }

        User user = event.getOption("user", OptionMapping::getAsUser);
        Role role = event.getOption("role", OptionMapping::getAsRole);

        if (user == null && role == null) {
            reply(event, "Please provide either a user or a role.");
            return;
        }

        GuildID guildID = new GuildID(guild.getIdLong());

        try {
            switch (subcommand) {
                case "add"    -> handleAdd(event, guildID, user, role);
                case "remove" -> handleRemove(event, guildID, user, role);
                default       -> reply(event, "Unknown subcommand.");
            }
        } catch (Exception e) {
            logger.error("Unexpected error in /exclude {}", subcommand, e);
            reply(event, "An unexpected error occurred. Please try again.");
        }
    }

    private void handleAdd(
            @NotNull SlashCommandInteractionEvent event,
            @NotNull GuildID guildID,
            User user,
            Role role
    ) {
        if (user != null) {
            boolean success = repository.markExcluded(guildID, UserID.fromUser(user));
            reply(event, success
                    ? "Excluded user " + user.getAsMention() + "."
                    : "Failed to exclude user. Please try again.");
            return;
        }

        boolean success = repository.markExcluded(guildID, RoleID.fromRole(role));
        reply(event, success
                ? "Excluded role " + role.getAsMention() + "."
                : "Failed to exclude role. Please try again.");
    }

    private void handleRemove(
            @NotNull SlashCommandInteractionEvent event,
            @NotNull GuildID guildID,
            User user,
            Role role
    ) {
        if (user != null) {
            boolean success = repository.unmarkExcluded(guildID, UserID.fromUser(user));
            reply(event, success
                    ? "Removed exclusion for user " + user.getAsMention() + "."
                    : "Failed to remove user exclusion. Please try again.");
            return;
        }

        boolean success = repository.unmarkExcluded(guildID, RoleID.fromRole(role));
        reply(event, success
                ? "Removed exclusion for role " + role.getAsMention() + "."
                : "Failed to remove role exclusion. Please try again.");
    }

    /**
     * Sends an ephemeral reply. All user-facing replies go through here to
     * ensure consistent behaviour and avoid repeating {@code setEphemeral(true)}.
     */
    private static void reply(@NotNull SlashCommandInteractionEvent event, @NotNull String message) {
        event.reply(message).setEphemeral(true).queue();
    }
}