package net.honeyberries.discord.slashCommands;

import net.dv8tion.jda.api.Permission;
import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.Member;
import net.dv8tion.jda.api.entities.channel.middleman.GuildChannel;
import net.dv8tion.jda.api.events.interaction.command.SlashCommandInteractionEvent;
import net.dv8tion.jda.api.hooks.ListenerAdapter;
import net.dv8tion.jda.api.interactions.commands.OptionMapping;
import net.dv8tion.jda.api.interactions.commands.OptionType;
import net.dv8tion.jda.api.interactions.commands.build.Commands;
import net.dv8tion.jda.api.interactions.commands.build.OptionData;
import net.dv8tion.jda.api.interactions.commands.build.SlashCommandData;
import net.dv8tion.jda.api.interactions.commands.build.SubcommandData;
import net.dv8tion.jda.api.requests.restaction.CommandListUpdateAction;
import net.honeyberries.database.SpecialUsersRepository;
import net.honeyberries.datatypes.action.ActionType;
import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.preferences.GuildPreferences;
import net.honeyberries.preferences.PreferencesHelper;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.Objects;

/**
 * Slash command handler for guild preference management.
 *
 * <p>Provides administrators with tools to configure guild-specific bot settings 
 * and preferences. Supports enabling/disabling AI, setting rules and audit channels,
 * and viewing current settings. Preferences control bot behavior specific to each guild.
 */
public class PreferencesCommands extends ListenerAdapter {

    private static final Logger logger = LoggerFactory.getLogger(PreferencesCommands.class);
    private final SpecialUsersRepository specialUsersRepo = SpecialUsersRepository.getInstance();
    /**
     * Registers the `/preferences` slash command with multiple subcommands for managing
     * guild preferences and settings.
     * <p>
     * The available subcommands include:
     * - `enable_ai`: Enable or disable AI moderation or view the current setting.
     * - `set_rules_channel`: Set the rules channel for the guild or view the current channel.
     * - `set_audit_channel`: Set the audit log channel for the guild or view the current channel.
     * - `settings`: View and manage guild preferences through a graphical interface.
     * - `reset`: Reset all preferences to their default values.
     * - `action`: Enable or disable specific moderation actions or view all available actions.
     * <p>
     * Each subcommand may include specific options to allow flexibility in usage.
     *
     * @param commands The {@link CommandListUpdateAction} instance used to register slash commands.
     *                 Must not be null.
     * @throws NullPointerException if the {@code commands} parameter is null.
     */
    public void registerPreferencesCommands(@NotNull CommandListUpdateAction commands) {
        Objects.requireNonNull(commands, "commands must not be null");

        SubcommandData enableAiSub = new SubcommandData(
                "enable_ai",
                "Enable or disable AI moderation (or view current setting)"
        ).addOptions(
                new OptionData(OptionType.BOOLEAN, "enabled", "Enable or disable AI (leave empty to view current)", false)
        );

        SubcommandData setRulesChannelSub = new SubcommandData(
                "set_rules_channel",
                "Set the rules channel for this guild (or view current channel)"
        ).addOptions(
                new OptionData(OptionType.CHANNEL, "channel", "Channel for rules (leave empty to view current)", false)
        );

        SubcommandData setAuditChannelSub = new SubcommandData(
                "set_audit_channel",
                "Set the audit log channel for this guild (or view current channel)"
        ).addOptions(
                new OptionData(OptionType.CHANNEL, "channel", "Channel for audit logs (leave empty to view current)", false)
        );

        SubcommandData settingsSub = new SubcommandData(
                "settings",
                "View and manage guild preferences with a graphical interface"
        );

        SubcommandData resetSub = new SubcommandData(
                "reset",
                "Reset all preferences to their default values"
        );

        SubcommandData actionSub = new SubcommandData(
                "action",
                "Enable or disable a specific moderation action (or view all actions)"
        ).addOptions(
                new OptionData(OptionType.STRING, "action", "The moderation action to toggle (leave empty to view all)", false)
                        .addChoice("warn", "warn")
                        .addChoice("timeout", "timeout")
                        .addChoice("delete", "delete")
                        .addChoice("kick", "kick")
                        .addChoice("ban", "ban"),
                new OptionData(OptionType.BOOLEAN, "enabled", "Enable or disable this action (leave empty to view current)", false)
        );

        SlashCommandData preferencesCommand = Commands.slash(
                "preferences",
                "Manage guild preferences and settings"
        ).addSubcommands(enableAiSub, setRulesChannelSub, setAuditChannelSub, settingsSub, resetSub, actionSub);

        Objects.requireNonNull(commands.addCommands(preferencesCommand));
        logger.info("Registered /preferences command with subcommands");
    }

    /**
     * Handles slash command interactions for the preferences command.
     *
     * <p>Routes to the appropriate subcommand handler (enable_ai, set_rules_channel,
     * set_audit_channel, or settings) after validating that the event is from a guild
     * and the invoker has administrator permissions.
     *
     * @param event the slash command interaction event. Must not be null.
     * @throws NullPointerException if event is null
     */
    @Override
    public void onSlashCommandInteraction(@NotNull SlashCommandInteractionEvent event) {
        Objects.requireNonNull(event, "event must not be null");
        if (!event.getName().equals("preferences")) {
            return;
        }

        // Guard: validate guild and permissions before processing
        Guild guild = validateGuildAndPermissions(event);
        if (guild == null) {
            return;
        }

        String subcommand = event.getSubcommandName();
        if (subcommand == null) {
            event.reply("Please specify a subcommand.").setEphemeral(true).queue();
            return;
        }

        try {
            switch (subcommand) {
                case "enable_ai" -> handleEnableAi(event, guild);
                case "set_rules_channel" -> handleSetRulesChannel(event, guild);
                case "set_audit_channel" -> handleSetAuditChannel(event, guild);
                case "settings" -> handleSettings(event);
                case "reset" -> handleReset(event, guild);
                case "action" -> handleAction(event, guild);
                default -> event.reply("Unknown subcommand").setEphemeral(true).queue();
            }
        } catch (Exception e) {
            logger.error("Error handling /preferences {}", subcommand, e);
            event.reply("An unexpected error occurred while processing the command.").setEphemeral(true).queue();
        }
    }

    /**
     * Validates that the event is from a guild and the invoker has adequate permissions.
     *
     * @param event the slash command interaction event
     * @return the Guild if validation passes, or null if validation fails (user already notified)
     */
    @Nullable
    private Guild validateGuildAndPermissions(@NotNull SlashCommandInteractionEvent event) {
        Guild guild = event.getGuild();
        if (guild == null) {
            event.reply("This command can only be used in servers!").setEphemeral(true).queue();
            return null;
        }

        Member member = event.getMember();
        if (member == null || (!member.hasPermission(Permission.MANAGE_SERVER)
                && !specialUsersRepo.isSpecialUser(event.getUser()))) {
            event.reply("You need the **Manage Server** permission or higher to use this command.").setEphemeral(true).queue();
            return null;
        }

        return guild;
    }


    /**
     * Handles the enable_ai subcommand.
     *
     * <p>Enables or disables AI moderation for the guild and persists the change
     * to the database. If no enabled option is provided, displays the current AI setting.
     *
     * @param event the slash command interaction event. Must not be null.
     * @param guild the guild where the command was invoked. Must not be null.
     * @throws NullPointerException if event or guild is null
     */
    private void handleEnableAi(@NotNull SlashCommandInteractionEvent event, @NotNull Guild guild) {
        Objects.requireNonNull(event, "event must not be null");
        Objects.requireNonNull(guild, "guild must not be null");
        try {
            GuildID guildId = new GuildID(guild.getIdLong());
            Boolean enabled = event.getOption("enabled", OptionMapping::getAsBoolean);

            // If no option provided, show current setting
            if (enabled == null) {
                GuildPreferences currentPrefs = PreferencesHelper.getInstance().getOrDefaultPreferences(guildId);
                String status = currentPrefs.aiEnabled() ? "**enabled**" : "**disabled**";
                event.reply("AI moderation is currently " + status + " for this guild.").setEphemeral(true).queue();
                return;
            }

            GuildPreferences updatedPrefs = PreferencesHelper.getInstance().getOrDefaultPreferences(guildId)
                    .withAiEnabled(enabled);

            if (PreferencesHelper.getInstance().updatePreferences(updatedPrefs)) {
                String status = enabled ? "enabled" : "disabled";
                event.reply("AI moderation has been **" + status + "** for this guild.").setEphemeral(true).queue();
                logger.debug("Guild {} AI moderation preference set to {}", guildId.value(), enabled);
            } else {
                event.reply(PreferencesMessages.UPDATE_FAILED).setEphemeral(true).queue();
            }
        } catch (Exception e) {
            logger.error("Error handling enable_ai subcommand", e);
            event.reply(PreferencesMessages.UPDATE_FAILED).setEphemeral(true).queue();
        }
    }



    /**
     * Handles the set_rules_channel subcommand.
     *
     * <p>Sets the rules channel for the guild and persists the change to the database.
     * If no channel option is provided, displays the currently configured rules channel.
     *
     * @param event the slash command interaction event. Must not be null.
     * @param guild the guild where the command was invoked. Must not be null.
     * @throws NullPointerException if event or guild is null
     */
    private void handleSetRulesChannel(@NotNull SlashCommandInteractionEvent event, @NotNull Guild guild) {
        Objects.requireNonNull(event, "event must not be null");
        Objects.requireNonNull(guild, "guild must not be null");
        try {
            GuildID guildId = new GuildID(guild.getIdLong());
            GuildChannel channel = event.getOption("channel", null, OptionMapping::getAsChannel);

            // If no option provided, show current setting
            if (channel == null) {
                GuildPreferences currentPrefs = PreferencesHelper.getInstance().getOrDefaultPreferences(guildId);
                displayCurrentChannel(event, guild, currentPrefs.rulesChannelID(), "Rules channel");
                return;
            }

            ChannelID channelId = new ChannelID(channel.getIdLong());
            GuildPreferences updatedPrefs = PreferencesHelper.getInstance().getOrDefaultPreferences(guildId)
                    .withRulesChannelId(channelId);

            if (PreferencesHelper.getInstance().updatePreferences(updatedPrefs)) {
                event.reply("Rules channel has been set to " + channel.getAsMention()).setEphemeral(true).queue();
                logger.debug("Guild {} rules channel set to {}", guildId.value(), channel.getId());
            } else {
                event.reply(PreferencesMessages.UPDATE_FAILED).setEphemeral(true).queue();
            }
        } catch (Exception e) {
            logger.error("Error handling set_rules_channel subcommand", e);
            event.reply(PreferencesMessages.UPDATE_FAILED).setEphemeral(true).queue();
        }
    }



    /**
     * Handles the set_audit_channel subcommand.
     *
     * <p>Sets the audit log channel for the guild and persists the change to the database.
     * If no channel option is provided, displays the currently configured audit channel.
     *
     * @param event the slash command interaction event. Must not be null.
     * @param guild the guild where the command was invoked. Must not be null.
     * @throws NullPointerException if event or guild is null
     */
    private void handleSetAuditChannel(@NotNull SlashCommandInteractionEvent event, @NotNull Guild guild) {
        Objects.requireNonNull(event, "event must not be null");
        Objects.requireNonNull(guild, "guild must not be null");
        try {
            GuildID guildId = new GuildID(guild.getIdLong());
            GuildChannel channel = event.getOption("channel", null, OptionMapping::getAsChannel);

            // If no option provided, show current setting
            if (channel == null) {
                GuildPreferences currentPrefs = PreferencesHelper.getInstance().getOrDefaultPreferences(guildId);
                displayCurrentChannel(event, guild, currentPrefs.auditLogChannelId(), "Audit log channel");
                return;
            }

            ChannelID channelId = new ChannelID(channel.getIdLong());
            GuildPreferences updatedPrefs = PreferencesHelper.getInstance().getOrDefaultPreferences(guildId)
                    .withAuditLogChannelId(channelId);

            if (PreferencesHelper.getInstance().updatePreferences(updatedPrefs)) {
                event.reply("Audit log channel has been set to " + channel.getAsMention()).setEphemeral(true).queue();
                logger.debug("Guild {} audit log channel set to {}", guildId.value(), channel.getId());
            } else {
                event.reply(PreferencesMessages.UPDATE_FAILED).setEphemeral(true).queue();
            }
        } catch (Exception e) {
            logger.error("Error handling set_audit_channel subcommand", e);
            event.reply(PreferencesMessages.UPDATE_FAILED).setEphemeral(true).queue();
        }
    }



    /**
     * Displays the current channel for a preference, handling missing channels gracefully.
     *
     * @param event the slash command interaction event
     * @param guild the guild context
     * @param channelId the channel ID to display, or null if not configured
     * @param channelType the human-readable name of the channel type (e.g., "Rules channel")
     */
    private void displayCurrentChannel(@NotNull SlashCommandInteractionEvent event, @NotNull Guild guild, @Nullable ChannelID channelId, @NotNull String channelType) {
        if (channelId == null) {
            event.reply("No " + channelType + " is currently configured.").setEphemeral(true).queue();
            return;
        }

        GuildChannel channel = guild.getGuildChannelById(channelId.value());
        if (channel != null) {
            event.reply(channelType + " is currently set to " + channel.getAsMention()).setEphemeral(true).queue();
        } else {
            event.reply(channelType + " is configured but no longer exists (ID: `" + channelId.value() + "`)").setEphemeral(true).queue();
        }
    }



    /**
     * Handles the settings subcommand.
     *
     * <p>Opens a graphical interface for managing guild preferences.
     * Currently a stub that requires implementation.
     *
     * @param event the slash command interaction event. Must not be null.
     * @throws NullPointerException if event is null
     */
    private void handleSettings(@NotNull SlashCommandInteractionEvent event) {
        Objects.requireNonNull(event, "event must not be null");
        // TODO: Implement GUI for preferences settings using JDA's interaction components
        // This should display current preferences with buttons to modify them
        event.reply("Settings GUI is not yet implemented.").setEphemeral(true).queue();
    }


    /**
     * Handles the reset subcommand.
     *
     * <p>Resets all guild preferences to their default values.
     *
     * @param event the slash command interaction event. Must not be null.
     * @param guild the guild where the command was invoked. Must not be null.
     * @throws NullPointerException if event or guild is null
     */
    private void handleReset(@NotNull SlashCommandInteractionEvent event, @NotNull Guild guild) {
        Objects.requireNonNull(event, "event must not be null");
        Objects.requireNonNull(guild, "guild must not be null");
        try {
            GuildID guildId = GuildID.fromGuild(guild);
            GuildPreferences defaultPrefs = GuildPreferences.defaults(guildId);

            if (PreferencesHelper.getInstance().updatePreferences(defaultPrefs)) {
                event.reply("All preferences have been reset to their default values.").setEphemeral(true).queue();
                logger.debug("Guild {} all preferences reset to defaults", guildId.value());
            } else {
                event.reply(PreferencesMessages.RESET_FAILED).setEphemeral(true).queue();
            }
        } catch (Exception e) {
            logger.error("Error handling reset subcommand", e);
            event.reply(PreferencesMessages.RESET_FAILED).setEphemeral(true).queue();
        }
    }



    /**
     * Handles the action subcommand.
     *
     * <p>Enables or disables a specific moderation action (warn, timeout, delete, kick, or ban)
     * for the guild. Routes to focused handlers based on which options are provided.
     *
     * @param event the slash command interaction event. Must not be null.
     * @param guild the guild where the command was invoked. Must not be null.
     * @throws NullPointerException if event or guild is null
     */
    private void handleAction(@NotNull SlashCommandInteractionEvent event, @NotNull Guild guild) {
        Objects.requireNonNull(event, "event must not be null");
        Objects.requireNonNull(guild, "guild must not be null");
        try {
            GuildID guildId = new GuildID(guild.getIdLong());
            String actionStr = event.getOption("action", OptionMapping::getAsString);
            Boolean enabled = event.getOption("enabled", OptionMapping::getAsBoolean);

            // Both null: show all actions
            if (actionStr == null && enabled == null) {
                handleActionViewAll(event, guildId);
                return;
            }

            // Action provided but enabled is null: show that action's current state
            if (actionStr != null && enabled == null) {
                handleActionViewOne(event, guildId, actionStr);
                return;
            }

            // Both provided: update the action
            if (actionStr != null) {
                handleActionUpdate(event, guildId, actionStr, enabled);
            }
        } catch (Exception e) {
            logger.error("Error handling action subcommand", e);
            event.reply(PreferencesMessages.UPDATE_FAILED).setEphemeral(true).queue();
        }
    }



    /**
     * Shows all available moderation actions and their current enabled/disabled status.
     *
     * @param event the slash command interaction event
     * @param guildId the guild ID
     */
    private void handleActionViewAll(@NotNull SlashCommandInteractionEvent event, @NotNull GuildID guildId) {
        GuildPreferences currentPrefs = PreferencesHelper.getInstance().getOrDefaultPreferences(guildId);

        ActionType[] actions = {ActionType.WARN, ActionType.TIMEOUT, ActionType.DELETE, ActionType.KICK, ActionType.BAN};
        StringBuilder allActionsMsg = new StringBuilder("**Current Moderation Actions:**\n");
        for (ActionType action : actions) {
            boolean actionEnabled = PreferencesHelper.getInstance().getActionEnabled(currentPrefs, action);
            String status = actionEnabled ? "✅ enabled" : "❌ disabled";
            allActionsMsg.append("• **").append(action.toString().toLowerCase()).append("**: ").append(status).append("\n");
        }

        event.reply(allActionsMsg.toString()).setEphemeral(true).queue();
    }



    /**
     * Shows the current enabled/disabled status of a specific moderation action.
     *
     * @param event the slash command interaction event
     * @param guildId the guild ID
     * @param actionStr the action string to display (e.g., "warn")
     */
    private void handleActionViewOne(@NotNull SlashCommandInteractionEvent event, @NotNull GuildID guildId, @NotNull String actionStr) {
        ActionType actionType = PreferencesHelper.getInstance().parseActionType(actionStr);
        if (actionType == null) {
            event.reply("Invalid action. Valid options are: warn, timeout, delete, kick, ban").setEphemeral(true).queue();
            return;
        }

        GuildPreferences currentPrefs = PreferencesHelper.getInstance().getOrDefaultPreferences(guildId);
        boolean actionEnabled = PreferencesHelper.getInstance().getActionEnabled(currentPrefs, actionType);
        String status = actionEnabled ? "**enabled**" : "**disabled**";
        event.reply("The **" + actionStr + "** action is currently " + status + ".").setEphemeral(true).queue();
    }



    /**
     * Updates the enabled/disabled status of a specific moderation action and persists the change.
     *
     * @param event the slash command interaction event
     * @param guildId the guild ID
     * @param actionStr the action string to update (e.g., "warn")
     * @param enabled the new enabled state
     */
    private void handleActionUpdate(@NotNull SlashCommandInteractionEvent event, @NotNull GuildID guildId, @NotNull String actionStr, boolean enabled) {
        ActionType actionType = PreferencesHelper.getInstance().parseActionType(actionStr);
        if (actionType == null) {
            event.reply("Invalid action. Valid options are: warn, timeout, delete, kick, ban").setEphemeral(true).queue();
            return;
        }

        GuildPreferences updatedPrefs = PreferencesHelper.getInstance().getOrDefaultPreferences(guildId);
        updatedPrefs = PreferencesHelper.getInstance().setActionEnabled(updatedPrefs, actionType, enabled);

        if (PreferencesHelper.getInstance().updatePreferences(updatedPrefs)) {
            String status = enabled ? "enabled" : "disabled";
            event.reply("The **" + actionStr + "** action has been **" + status + "**.").setEphemeral(true).queue();
            logger.debug("Guild {} action {} set to {}", guildId.value(), actionStr, enabled);
        } else {
            event.reply(PreferencesMessages.UPDATE_FAILED).setEphemeral(true).queue();
        }
    }




    /**
     * Centralized message constants for consistent user-facing text.
     */
    private static final class PreferencesMessages {
        static final String UPDATE_FAILED = "Failed to update preference. Please try again.";
        static final String RESET_FAILED = "Failed to reset preferences. Please try again.";
    }

}
