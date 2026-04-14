package net.honeyberries.discord.slashCommands;

import net.dv8tion.jda.api.Permission;
import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.Member;
import net.dv8tion.jda.api.entities.Role;
import net.dv8tion.jda.api.entities.User;
import net.dv8tion.jda.api.entities.channel.middleman.MessageChannel;
import net.dv8tion.jda.api.entities.channel.unions.GuildChannelUnion;
import net.dv8tion.jda.api.events.interaction.command.SlashCommandInteractionEvent;
import net.dv8tion.jda.api.hooks.ListenerAdapter;
import net.dv8tion.jda.api.interactions.commands.OptionMapping;
import net.dv8tion.jda.api.interactions.commands.OptionType;
import net.dv8tion.jda.api.interactions.commands.build.Commands;
import net.dv8tion.jda.api.interactions.commands.build.OptionData;
import net.dv8tion.jda.api.interactions.commands.build.SlashCommandData;
import net.dv8tion.jda.api.interactions.commands.build.SubcommandData;
import net.dv8tion.jda.api.requests.restaction.CommandListUpdateAction;
import net.honeyberries.database.ExcludedEntitiesRepository;
import net.honeyberries.database.SpecialUsersRepository;
import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.discord.RoleID;
import net.honeyberries.datatypes.discord.UserID;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;

/**
 * Slash command handler for managing moderation exclusions.
 *
 * <p>Allows administrators to create an exclusion list of users, roles, and channels that should
 * be protected from automated moderation. This command supports batch operations: you can exclude
 * or unexclude multiple users, multiple roles, multiple channels, or any combination in one invocation.
 * Users on the exclusion list are checked with higher priority than roles. This provides
 * fine-grained control over moderation scope and helps protect VIPs, sensitive accounts, or
 * specific channels from automated actions.
 *
 * <p>Requires the invoking member to have {@link Permission#ADMINISTRATOR}.
 */
public class ExcludeCommand extends ListenerAdapter {

    private static final Logger logger = LoggerFactory.getLogger(ExcludeCommand.class);
    private final ExcludedEntitiesRepository repository = ExcludedEntitiesRepository.getInstance();

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
        OptionData channelOption = new OptionData(OptionType.CHANNEL, "channel", "Target channel", false);

        SlashCommandData excludeCommand = Commands.slash("exclude", "Manage moderation exclusions")
                .addSubcommands(
                        new SubcommandData("add", "Exclude users, roles, and/or channels from moderation")
                                .addOptions(userOption, roleOption, channelOption),
                        new SubcommandData("remove", "Remove users, roles, and/or channels from exclusion")
                                .addOptions(userOption, roleOption, channelOption),
                        new SubcommandData("list", "Show excluded users, roles, and channels")
                );

        Objects.requireNonNull(commands.addCommands(excludeCommand));
        logger.info("Registered /exclude commands");
    }

    /**
     * Handles slash command interactions for the exclude command.
     *
     * <p>Routes to appropriate subcommand handler (add, remove, or list) after validating
     * that the event is from a guild, the invoker has administrator permissions, and a
     * valid subcommand with at least one argument is provided.
     *
     * <p>Supports batch operations: add/remove can process multiple users, roles, and/or
     * channels in a single invocation.
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
            GuildChannelUnion channel = event.getOption("channel", OptionMapping::getAsChannel);

            if (user == null && role == null && channel == null) {
                reply(event, "Please provide at least one user, role, or channel.");
                return;
            }

            switch (subcommand) {
                case "add"    -> handleAdd(event, guildID, user, role, channel);
                case "remove" -> handleRemove(event, guildID, user, role, channel);
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
     * <p>Adds users, roles, and/or channels to the moderation exclusion list for the guild.
     * Supports batch operations: you can add multiple entities in a single invocation by
     * providing a user, role, and channel simultaneously. Reports success/failure for each
     * entity type separately.
     *
     * @param event the slash command interaction event. Must not be null.
     * @param guildID the ID of the guild. Must not be null.
     * @param user the user to exclude, or null if not excluding a user.
     * @param role the role to exclude, or null if not excluding a role.
     * @param channel the channel to exclude, or null if not excluding a channel.
     * @throws NullPointerException if event or guildID is null
     */
    private void handleAdd(
            @NotNull SlashCommandInteractionEvent event,
            @NotNull GuildID guildID,
            @Nullable User user,
            @Nullable Role role,
            @Nullable GuildChannelUnion channel
    ) {
        Objects.requireNonNull(event, "event must not be null");
        Objects.requireNonNull(guildID, "guildID must not be null");

        List<String> results = new ArrayList<>();

        if (user != null) {
            boolean success = repository.markExcluded(guildID, UserID.fromUser(user));
            results.add(success
                    ? "✓ Excluded user " + user.getAsMention()
                    : "✗ Failed to exclude user " + user.getAsMention());
        }

        if (role != null) {
            boolean success = repository.markExcluded(guildID, RoleID.fromRole(role));
            results.add(success
                    ? "✓ Excluded role " + role.getAsMention()
                    : "✗ Failed to exclude role " + role.getAsMention());
        }

        if (channel != null) {
            if (channel instanceof MessageChannel msgChannel) {
                boolean success = repository.markExcluded(guildID, ChannelID.fromChannel(msgChannel));
                results.add(success
                        ? "✓ Excluded channel " + channel.getAsMention()
                        : "✗ Failed to exclude channel " + channel.getAsMention());
            } else {
                results.add("✗ Channel type cannot be excluded: " + channel.getAsMention());
            }
        }

        String message = results.isEmpty()
                ? "No changes made."
                : String.join("\n", results);
        reply(event, message);
    }

    /**
     * Handles the remove subcommand.
     *
     * <p>Removes users, roles, and/or channels from the moderation exclusion list for the guild.
     * Supports batch operations: you can remove multiple entities in a single invocation by
     * providing a user, role, and channel simultaneously. Reports success/failure for each
     * entity type separately.
     *
     * @param event the slash command interaction event. Must not be null.
     * @param guildID the ID of the guild. Must not be null.
     * @param user the user to unexclude, or null if not removing a user exclusion.
     * @param role the role to unexclude, or null if not removing a role exclusion.
     * @param channel the channel to unexclude, or null if not removing a channel exclusion.
     * @throws NullPointerException if event or guildID is null
     */
    private void handleRemove(
            @NotNull SlashCommandInteractionEvent event,
            @NotNull GuildID guildID,
            @Nullable User user,
            @Nullable Role role,
            @Nullable GuildChannelUnion channel
    ) {
        Objects.requireNonNull(event, "event must not be null");
        Objects.requireNonNull(guildID, "guildID must not be null");

        List<String> results = new ArrayList<>();

        if (user != null) {
            boolean success = repository.unmarkExcluded(guildID, UserID.fromUser(user));
            results.add(success
                    ? "✓ Removed exclusion for user " + user.getAsMention()
                    : "✗ Failed to remove user exclusion: " + user.getAsMention());
        }

        if (role != null) {
            boolean success = repository.unmarkExcluded(guildID, RoleID.fromRole(role));
            results.add(success
                    ? "✓ Removed exclusion for role " + role.getAsMention()
                    : "✗ Failed to remove role exclusion: " + role.getAsMention());
        }

        if (channel != null) {
            if (channel instanceof MessageChannel msgChannel) {
                boolean success = repository.unmarkExcluded(guildID, ChannelID.fromChannel(msgChannel));
                results.add(success
                        ? "✓ Removed exclusion for channel " + channel.getAsMention()
                        : "✗ Failed to remove channel exclusion: " + channel.getAsMention());
            } else {
                results.add("✗ Channel type cannot be excluded: " + channel.getAsMention());
            }
        }

        String message = results.isEmpty()
                ? "No changes made."
                : String.join("\n", results);
        reply(event, message);
    }

    /**
     * Handles the list subcommand.
     *
     * <p>Displays all currently excluded users, roles, and channels for the guild, formatted
     * as mentions. Users are shown with highest priority, followed by roles, then channels.
     * If no exclusions exist, displays a message indicating the server has no exclusions.
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
        ExcludedEntitiesRepository.ExcludedEntities excluded = repository.getExcludedEntities(guildID);

        if (excluded.userIDs().isEmpty() && excluded.roleIDs().isEmpty() && excluded.channelIDs().isEmpty()) {
            reply(event, "There are no excluded users, roles, or channels in this server.");
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

        String channelsSection = excluded.channelIDs().isEmpty()
                ? "None"
                : excluded.channelIDs().stream()
                  .map(channelID -> formatChannelMention(guild, channelID))
                  .collect(Collectors.joining("\n"));

        String message = "**Excluded users (highest priority):**\n"
                + usersSection
                + "\n\n**Excluded roles:**\n"
                + rolesSection
                + "\n\n**Excluded channels:**\n"
                + channelsSection;

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
     * Formats a channel ID as a mention string.
     *
     * <p>Attempts to retrieve the channel from the guild. If the channel has been deleted,
     * indicates this in the formatted output.
     *
     * @param guild the guild to look up the channel in. Must not be null.
     * @param channelId the ID of the channel. Must not be null.
     * @return a formatted mention string
     * @throws NullPointerException if guild or channelId is null
     */
    @NotNull
    private static String formatChannelMention(@NotNull Guild guild, @NotNull ChannelID channelId) {
        Objects.requireNonNull(guild, "guild must not be null");
        Objects.requireNonNull(channelId, "channelId must not be null");
        if (guild.getGuildChannelById(channelId.value()) != null) {
            return "- <#" + channelId.value() + ">";
        }
        return "- <#" + channelId.value() + "> (deleted channel)";
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