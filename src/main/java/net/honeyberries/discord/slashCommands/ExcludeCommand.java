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

import java.util.stream.Collectors;

/**
 * Slash command handler for managing moderation exclusions.
 *
 * <p>Requires the invoking member to have {@link Permission#ADMINISTRATOR}.
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
                                .addOptions(userOption, roleOption),
                        new SubcommandData("list", "Show excluded users and roles")
                );


        commands.addCommands(excludeCommand);
        logger.info("Registered /exclude commands");
    }

    @Override
    public void onSlashCommandInteraction(@NotNull SlashCommandInteractionEvent event) {
        String commandName = event.getName();
        if (!commandName.equals("exclude")) return;

        Guild guild = event.getGuild();
        if (guild == null) {
            reply(event, "This command can only be used in servers!");
            return;
        }

        Member member = event.getMember();
        if (member == null || !member.hasPermission(Permission.ADMINISTRATOR)) {
            reply(event, "You need **Administrator** permissions to use this command.");
            return;
        }

        String subcommand = event.getSubcommandName();
        if (subcommand == null) {
            reply(event, "Please specify a subcommand.");
            return;
        }

        GuildID guildID = new GuildID(guild.getIdLong());

        try {
            if (subcommand.equals("list")) {
                handleList(event, guild, guildID);
                return;
            }

            User user = event.getOption("user", OptionMapping::getAsUser);
            Role role = event.getOption("role", OptionMapping::getAsRole);

            if (user == null && role == null) {
                reply(event, "Please provide either a user or a role.");
                return;
            }

            if (user != null && role != null) {
                reply(event, "Please provide either a user or a role, not both.");
                return;
            }

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

    private void handleList(
            @NotNull SlashCommandInteractionEvent event,
            @NotNull Guild guild,
            @NotNull GuildID guildID
    ) {
        ExcludedUsersRepository.ExcludedEntities excluded = repository.getExcludedEntities(guildID);

        if (excluded.userIDs().isEmpty() && excluded.roleIDs().isEmpty()) {
            reply(event, "There are no excluded users or roles in this server.");
            return;
        }

        String usersSection = excluded.userIDs().isEmpty()
                ? "None"
                : excluded.userIDs().stream()
                .map(userID -> formatUserMention(guild, userID))
                .collect(Collectors.joining("\n"));

        String rolesSection = excluded.roleIDs().isEmpty()
                ? "None"
                : excluded.roleIDs().stream()
                .map(roleID -> formatRoleMention(guild, roleID))
                .collect(Collectors.joining("\n"));

        String message = "**Excluded users (higher priority):**\n"
                + usersSection
                + "\n\n**Excluded roles:**\n"
                + rolesSection;

        reply(event, message);
    }

    private static String formatUserMention(@NotNull Guild guild, UserID userId) {
        if (guild.retrieveMemberById(userId.value()).complete() != null) {
            return "- <@" + userId.value() + ">";
        }
        return "- <@" + userId.value() + "> (not in server or deleted user)";
    }

    private static String formatRoleMention(@NotNull Guild guild, RoleID roleId) {
        if (guild.getRoleById(roleId.value()) != null) {
            return "- <@&" + roleId.value() + ">";
        }
        return "- <@&" + roleId.value() + "> (deleted role)";
    }

    /**
     * Sends an ephemeral reply. All user-facing replies go through here to
     * ensure consistent behaviour and avoid repeating {@code setEphemeral(true)}.
     */
    private static void reply(@NotNull SlashCommandInteractionEvent event, @NotNull String message) {
        event.reply(message).setEphemeral(true).queue();
    }
}