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
import net.honeyberries.database.SpecialUsersRepository;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.discord.RoleID;
import net.honeyberries.datatypes.discord.UserID;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.Objects;
import java.util.stream.Collectors;

/**
 * Slash command handler for managing moderation exclusions.
 *
 * <p>Allows administrators to create an exclusion list of users and roles that should 
 * be protected from automated moderation. Users on the exclusion list are checked with 
 * higher priority than roles. This provides fine-grained control over moderation scope 
 * and helps protect VIPs or sensitive accounts from automated actions.
 *
 * <p>Requires the invoking member to have {@link Permission#ADMINISTRATOR}.
 */
public class ExcludeCommand extends ListenerAdapter {

    private static final Logger logger = LoggerFactory.getLogger(ExcludeCommand.class);
    private final ExcludedUsersRepository repository = ExcludedUsersRepository.getInstance();

    /**
     * Registers the exclude command and its subcommands with the Discord bot.
     *
     * @param commands the command list update action to register commands with. Must not be null.
     * @throws NullPointerException if commands is null
     */
    public void registerExcludeCommands(@NotNull CommandListUpdateAction commands) {
        Objects.requireNonNull(commands, "commands must not be null");
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


        Objects.requireNonNull(commands.addCommands(excludeCommand));
        logger.info("Registered /exclude commands");
    }

    /**
     * Handles slash command interactions for the exclude command.
     *
     * <p>Routes to appropriate subcommand handler (add, remove, or list) after validating 
     * that the event is from a guild, the invoker has administrator permissions, and a 
     * valid subcommand with required arguments is provided.
     *
     * @param event the slash command interaction event. Must not be null.
     * @throws NullPointerException if event is null
     */
    @Override
    public void onSlashCommandInteraction(@NotNull SlashCommandInteractionEvent event) {
        Objects.requireNonNull(event, "event must not be null");
        String commandName = event.getName();
        if (!commandName.equals("exclude")) return;

        Guild guild = event.getGuild();
        if (guild == null) {
            reply(event, "This command can only be used in servers!");
            return;
        }

        Member member = event.getMember();
        if (member == null || (!member.hasPermission(Permission.MANAGE_SERVER)
                && !SpecialUsersRepository.getInstance().isSpecialUser(event.getUser()))) {
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

    /**
     * Handles the add subcommand.
     *
     * <p>Adds a user or role to the moderation exclusion list for the guild. Exactly one 
     * of user or role must be provided (not both). Replies with success or failure status.
     *
     * @param event the slash command interaction event. Must not be null.
     * @param guildID the ID of the guild. Must not be null.
     * @param user the user to exclude, or null if excluding a role. Mutually exclusive with role.
     * @param role the role to exclude, or null if excluding a user. Mutually exclusive with user.
     * @throws NullPointerException if event or guildID is null
     */
    private void handleAdd(
            @NotNull SlashCommandInteractionEvent event,
            @NotNull GuildID guildID,
            @Nullable User user,
            @Nullable Role role
    ) {
        Objects.requireNonNull(event, "event must not be null");
        Objects.requireNonNull(guildID, "guildID must not be null");
        if (user != null) {
            boolean success = repository.markExcluded(guildID, UserID.fromUser(user));
            reply(event, success
                    ? "Excluded user " + user.getAsMention() + "."
                    : "Failed to exclude user. Please try again.");
            return;
        }

        boolean success = repository.markExcluded(guildID, RoleID.fromRole(Objects.requireNonNull(role, "role must not be null")));
        reply(event, success
                ? "Excluded role " + role.getAsMention() + "."
                : "Failed to exclude role. Please try again.");
    }

    /**
     * Handles the remove subcommand.
     *
     * <p>Removes a user or role from the moderation exclusion list for the guild. Exactly 
     * one of user or role must be provided (not both). Replies with success or failure status.
     *
     * @param event the slash command interaction event. Must not be null.
     * @param guildID the ID of the guild. Must not be null.
     * @param user the user to unexclude, or null if unexcluding a role. Mutually exclusive with role.
     * @param role the role to unexclude, or null if unexcluding a user. Mutually exclusive with user.
     * @throws NullPointerException if event or guildID is null
     */
    private void handleRemove(
            @NotNull SlashCommandInteractionEvent event,
            @NotNull GuildID guildID,
            @Nullable User user,
            @Nullable Role role
    ) {
        Objects.requireNonNull(event, "event must not be null");
        Objects.requireNonNull(guildID, "guildID must not be null");
        if (user != null) {
            boolean success = repository.unmarkExcluded(guildID, UserID.fromUser(user));
            reply(event, success
                    ? "Removed exclusion for user " + user.getAsMention() + "."
                    : "Failed to remove user exclusion. Please try again.");
            return;
        }

        boolean success = repository.unmarkExcluded(guildID, RoleID.fromRole(Objects.requireNonNull(role, "role must not be null")));
        reply(event, success
                ? "Removed exclusion for role " + role.getAsMention() + "."
                : "Failed to remove role exclusion. Please try again.");
    }

    /**
     * Handles the list subcommand.
     *
     * <p>Displays all currently excluded users and roles for the guild, formatted as 
     * mentions. Users are shown with higher priority. If no exclusions exist, displays 
     * a message indicating the server has no exclusions.
     *
     * @param event the slash command interaction event. Must not be null.
     * @param guild the guild to list exclusions for. Must not be null.
     * @param guildID the ID of the guild. Must not be null.
     * @throws NullPointerException if any parameter is null
     */
    private void handleList(
            @NotNull SlashCommandInteractionEvent event,
            @NotNull Guild guild,
            @NotNull GuildID guildID
    ) {
        Objects.requireNonNull(event, "event must not be null");
        Objects.requireNonNull(guild, "guild must not be null");
        Objects.requireNonNull(guildID, "guildID must not be null");
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

    /**
     * Formats a user ID as a mention string.
     *
     * <p>Attempts to retrieve the member from the guild. If the member is not found or 
     * has been deleted, indicates this in the formatted output.
     *
     * @param guild the guild to look up the user in. Must not be null.
     * @param userId the ID of the user. Must not be null.
     * @return a formatted mention string
     * @throws NullPointerException if guild or userId is null
     */
    @NotNull
    private static String formatUserMention(@NotNull Guild guild, @NotNull UserID userId) {
        Objects.requireNonNull(guild, "guild must not be null");
        Objects.requireNonNull(userId, "userId must not be null");
        if (guild.retrieveMemberById(userId.value()).complete() != null) {
            return "- <@" + userId.value() + ">";
        }
        return "- <@" + userId.value() + "> (not in server or deleted user)";
    }

    /**
     * Formats a role ID as a mention string.
     *
     * <p>Attempts to retrieve the role from the guild. If the role has been deleted, 
     * indicates this in the formatted output.
     *
     * @param guild the guild to look up the role in. Must not be null.
     * @param roleId the ID of the role. Must not be null.
     * @return a formatted mention string
     * @throws NullPointerException if guild or roleId is null
     */
    @NotNull
    private static String formatRoleMention(@NotNull Guild guild, @NotNull RoleID roleId) {
        Objects.requireNonNull(guild, "guild must not be null");
        Objects.requireNonNull(roleId, "roleId must not be null");
        if (guild.getRoleById(roleId.value()) != null) {
            return "- <@&" + roleId.value() + ">";
        }
        return "- <@&" + roleId.value() + "> (deleted role)";
    }

    /**
     * Sends an ephemeral reply to a slash command interaction.
     *
     * <p>All user-facing replies from exclude commands go through here to ensure 
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