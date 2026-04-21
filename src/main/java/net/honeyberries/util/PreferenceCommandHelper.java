package net.honeyberries.util;

import net.dv8tion.jda.api.Permission;
import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.Member;
import net.dv8tion.jda.api.entities.channel.middleman.GuildChannel;
import net.dv8tion.jda.api.events.interaction.command.SlashCommandInteractionEvent;
import net.dv8tion.jda.api.events.interaction.component.ButtonInteractionEvent;
import net.dv8tion.jda.api.events.interaction.component.EntitySelectInteractionEvent;
import net.dv8tion.jda.api.events.interaction.component.StringSelectInteractionEvent;
import net.dv8tion.jda.api.interactions.commands.OptionMapping;
import net.honeyberries.database.repository.SpecialUsersRepository;
import net.honeyberries.datatypes.action.ActionType;
import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.preferences.GuildPreferences;
import net.honeyberries.discord.slashCommands.PreferencesCommands;
import net.honeyberries.preferences.PreferencesManager;
import net.honeyberries.ui.PreferencesEmbedUI;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.Objects;

/**
 * Business-logic helper for the {@code /preferences} slash command.
 *
 * <p>Provides handlers for all preference-related subcommands and interactions, delegating
 * to this class from {@link PreferencesCommands} to keep business logic separate from
 * Discord event routing. All methods are package-private to enforce delegation patterns.</p>
 *
 * <p><strong>Responsibilities:</strong></p>
 * <ul>
 *   <li>Permission validation ({@link Permission#MANAGE_SERVER} or special user status)</li>
 *   <li>Guild preference CRUD operations (enable AI, set channels, configure actions)</li>
 *   <li>Settings UI construction (embeds, buttons, select menus)</li>
 *   <li>Component interaction handling (button clicks, selections)</li>
 *   <li>Guild preference reset and query functionality</li>
 * </ul>
 */
public class PreferenceCommandHelper {

    private static final Logger logger = LoggerFactory.getLogger(PreferenceCommandHelper.class);

    private final SpecialUsersRepository specialUsersRepo = SpecialUsersRepository.getInstance();

    // =========================================================================
    // Permission Validation
    // =========================================================================

    /**
     * Validates that the event originates from a guild and that the invoker holds
     * {@link Permission#MANAGE_SERVER} or is a special user.
     *
     * <p>If validation fails, sends an ephemeral error response to the user.</p>
     *
     * @param event the slash command interaction event from Discord
     * @return the {@link Guild} if validation passes; {@code null} if validation fails
     *         (error response already queued to Discord)
     */
    @Nullable
    public Guild validateGuildAndPermissions(@NotNull SlashCommandInteractionEvent event) {
        Objects.requireNonNull(event, "event must not be null");

        Guild guild = event.getGuild();
        if (guild == null) {
            event.reply("This command can only be used in servers!").setEphemeral(true).queue();
            return null;
        }

        Member member = event.getMember();
        if (member == null || (!member.hasPermission(Permission.MANAGE_SERVER)
                && !specialUsersRepo.isSpecialUser(event.getUser()))) {
            event.reply("You need the **Manage Server** permission or higher to use this command.")
                    .setEphemeral(true).queue();
            return null;
        }

        return guild;
    }

    // =========================================================================
    // Subcommand Handlers: Basic Settings
    // =========================================================================

    /**
     * Handles the {@code /preferences enable_ai} subcommand.
     *
     * <p>If {@code enabled} is omitted, reports the current setting. Otherwise,
     * enables or disables AI moderation for the guild.</p>
     *
     * @param event the slash command interaction event
     * @param guild the guild where the command was invoked (validated)
     * @throws NullPointerException if event or guild is null
     */
    public void handleEnableAi(@NotNull SlashCommandInteractionEvent event, @NotNull Guild guild) {
        Objects.requireNonNull(event, "event must not be null");
        Objects.requireNonNull(guild, "guild must not be null");
        try {
            GuildID guildId = GuildID.fromGuild(guild);
            Boolean enabled = event.getOption("enabled", OptionMapping::getAsBoolean);

            if (enabled == null) {
                reportAiStatus(event, guildId);
                return;
            }

            updateAiStatus(event, guildId, enabled);
        } catch (Exception e) {
            logger.error("Error handling enable_ai subcommand", e);
            event.reply(PreferencesCommands.PreferencesMessages.UPDATE_FAILED)
                    .setEphemeral(true).queue();
        }
    }

    /**
     * Handles the {@code /preferences set_rules_channel} subcommand.
     *
     * <p>If {@code channel} is omitted, reports the currently configured channel.
     * Otherwise, sets the rules channel for the guild.</p>
     *
     * @param event the slash command interaction event
     * @param guild the guild where the command was invoked (validated)
     * @throws NullPointerException if event or guild is null
     */
    public void handleSetRulesChannel(@NotNull SlashCommandInteractionEvent event, @NotNull Guild guild) {
        Objects.requireNonNull(event, "event must not be null");
        Objects.requireNonNull(guild, "guild must not be null");
        try {
            GuildID guildId = GuildID.fromGuild(guild);
            GuildChannel channel = event.getOption("channel", null, OptionMapping::getAsChannel);

            if (channel == null) {
                GuildPreferences prefs = PreferencesManager.getInstance().getOrDefaultPreferences(guildId);
                displayCurrentChannel(event, guild, prefs.rulesChannelID(), "Rules channel");
                return;
            }

            updateRulesChannel(event, guildId, channel);
        } catch (Exception e) {
            logger.error("Error handling set_rules_channel subcommand", e);
            event.reply(PreferencesCommands.PreferencesMessages.UPDATE_FAILED)
                    .setEphemeral(true).queue();
        }
    }

    /**
     * Handles the {@code /preferences set_audit_channel} subcommand.
     *
     * <p>If {@code channel} is omitted, reports the currently configured channel.
     * Otherwise, sets the audit-log channel for the guild.</p>
     *
     * @param event the slash command interaction event
     * @param guild the guild where the command was invoked (validated)
     * @throws NullPointerException if event or guild is null
     */
    public void handleSetAuditChannel(@NotNull SlashCommandInteractionEvent event, @NotNull Guild guild) {
        Objects.requireNonNull(event, "event must not be null");
        Objects.requireNonNull(guild, "guild must not be null");
        try {
            GuildID guildId = GuildID.fromGuild(guild);
            GuildChannel channel = event.getOption("channel", null, OptionMapping::getAsChannel);

            if (channel == null) {
                GuildPreferences prefs = PreferencesManager.getInstance().getOrDefaultPreferences(guildId);
                displayCurrentChannel(event, guild, prefs.auditLogChannelId(), "Audit log channel");
                return;
            }

            updateAuditChannel(event, guildId, channel);
        } catch (Exception e) {
            logger.error("Error handling set_audit_channel subcommand", e);
            event.reply(PreferencesCommands.PreferencesMessages.UPDATE_FAILED)
                    .setEphemeral(true).queue();
        }
    }

    // =========================================================================
    // Subcommand Handlers: Actions
    // =========================================================================

    /**
     * Handles the {@code /preferences action} subcommand.
     *
     * <p>Routes to sub-handlers based on provided options:</p>
     * <ul>
     *   <li>Neither {@code action} nor {@code enabled}: show all actions and their states</li>
     *   <li>{@code action} only: show that action's current state</li>
     *   <li>Both provided: update the action's enabled state</li>
     * </ul>
     *
     * @param event the slash command interaction event
     * @param guild the guild where the command was invoked (validated)
     * @throws NullPointerException if event or guild is null
     */
    public void handleAction(@NotNull SlashCommandInteractionEvent event, @NotNull Guild guild) {
        Objects.requireNonNull(event, "event must not be null");
        Objects.requireNonNull(guild, "guild must not be null");
        try {
            GuildID guildId = GuildID.fromGuild(guild);
            String actionStr = event.getOption("action", OptionMapping::getAsString);
            Boolean enabled = event.getOption("enabled", OptionMapping::getAsBoolean);

            if (actionStr == null && enabled == null) {
                handleActionViewAll(event, guildId);
            } else if (actionStr != null && enabled == null) {
                handleActionViewOne(event, guildId, actionStr);
            } else if (actionStr != null) {
                handleActionUpdate(event, guildId, actionStr, enabled);
            } else {
                event.reply("Please specify an action to enable or disable.").setEphemeral(true).queue();
            }
        } catch (Exception e) {
            logger.error("Error handling action subcommand", e);
            event.reply(PreferencesCommands.PreferencesMessages.UPDATE_FAILED)
                    .setEphemeral(true).queue();
        }
    }

    /**
     * Handles the {@code /preferences reset} subcommand.
     *
     * <p>Resets all guild preferences to their default values.</p>
     *
     * @param event the slash command interaction event
     * @param guild the guild where the command was invoked (validated)
     * @throws NullPointerException if event or guild is null
     */
    public void handleReset(@NotNull SlashCommandInteractionEvent event, @NotNull Guild guild) {
        Objects.requireNonNull(event, "event must not be null");
        Objects.requireNonNull(guild, "guild must not be null");
        try {
            GuildID guildId = GuildID.fromGuild(guild);
            GuildPreferences defaultPrefs = GuildPreferences.defaults(guildId);

            if (PreferencesManager.getInstance().updatePreferences(defaultPrefs)) {
                event.reply("All preferences have been reset to their default values.")
                        .setEphemeral(true).queue();
                logger.debug("Guild {} preferences reset to defaults", guildId.value());
            } else {
                event.reply(PreferencesCommands.PreferencesMessages.RESET_FAILED)
                        .setEphemeral(true).queue();
            }
        } catch (Exception e) {
            logger.error("Error handling reset subcommand", e);
            event.reply(PreferencesCommands.PreferencesMessages.RESET_FAILED).setEphemeral(true).queue();
        }
    }

    // =========================================================================
    // Subcommand Handlers: Settings GUI
    // =========================================================================

    /**
     * Handles the {@code /preferences settings} subcommand.
     *
     * <p>Displays the interactive settings GUI with embeds and component-based
     * navigation. Uses button toggles, entity select menus, and string select menus
     * to allow users to manage preferences interactively.</p>
     *
     * @param event the slash command interaction event
     */
    public void handleSettings(@NotNull SlashCommandInteractionEvent event) {
        Objects.requireNonNull(event, "event must not be null");
        Guild guild = event.getGuild();
        if (guild == null) {
            return;
        }

        GuildID guildId = GuildID.fromGuild(guild);
        String category = "general";

        event.replyEmbeds(PreferencesEmbedUI.buildSettingsEmbed(category))
                .setComponents(PreferencesEmbedUI.buildSettingsComponents(guildId, category))
                .setEphemeral(true).queue();
    }

    // =========================================================================
    // Component Interaction Handlers
    // =========================================================================

    /**
     * Handles button interactions in the preferences settings UI.
     *
     * <p>Supports:</p>
     * <ul>
     *   <li>{@code pref_ai_toggle}: toggle AI moderation on/off</li>
     *   <li>{@code pref_action_*}: toggle specific moderation actions</li>
     * </ul>
     *
     * @param event the button interaction event
     */
    public void handleButtonInteraction(@NotNull ButtonInteractionEvent event) {
        Objects.requireNonNull(event, "event must not be null");

        Guild guild = event.getGuild();
        if (guild == null) {
            return;
        }

        GuildID guildId = GuildID.fromGuild(guild);
        String componentId = event.getComponentId();

        if (componentId.equals("pref_ai_toggle")) {
            handleAiToggleButton(event, guildId);
        } else if (componentId.startsWith("pref_action_")) {
            handleActionToggleButton(event, guildId, componentId);
        }
    }

    /**
     * Handles string select menu interactions in the preferences settings UI.
     *
     * <p>Supports:</p>
     * <ul>
     *   <li>{@code pref_nav}: category navigation (general, actions)</li>
     * </ul>
     *
     * @param event the string select interaction event
     */
    public void handleStringSelectInteraction(@NotNull StringSelectInteractionEvent event) {
        Objects.requireNonNull(event, "event must not be null");

        Guild guild = event.getGuild();
        if (guild == null) {
            return;
        }

        GuildID guildId = GuildID.fromGuild(guild);
        String componentId = event.getComponentId();

        if (componentId.equals("pref_nav")) {
            String category = event.getValues().getFirst();
            event.editMessageEmbeds(PreferencesEmbedUI.buildSettingsEmbed(category))
                    .setComponents(PreferencesEmbedUI.buildSettingsComponents(guildId, category)).queue();
        }
    }

    /**
     * Handles entity select menu interactions in the preferences settings UI.
     *
     * <p>Supports:</p>
     * <ul>
     *   <li>{@code pref_rules_channel}: select the rules channel</li>
     *   <li>{@code pref_audit_channel}: select the audit log channel</li>
     * </ul>
     *
     * @param event the entity select interaction event
     */
    public void handleEntitySelectInteraction(@NotNull EntitySelectInteractionEvent event) {
        Objects.requireNonNull(event, "event must not be null");

        Guild guild = event.getGuild();
        if (guild == null) {
            return;
        }

        GuildID guildId = GuildID.fromGuild(guild);
        String componentId = event.getComponentId();

        if ((componentId.equals("pref_rules_channel") || componentId.equals("pref_audit_channel"))
                && !event.getValues().isEmpty()) {
            handleChannelSelection(event, guildId, componentId);
        }

        event.editMessageEmbeds(PreferencesEmbedUI.buildSettingsEmbed("general"))
                .setComponents(PreferencesEmbedUI.buildSettingsComponents(guildId, "general")).queue();
    }


    // =========================================================================
    // Action Subcommand Sub-handlers
    // =========================================================================

    /**
     * Displays all moderation actions and their enabled/disabled states.
     *
     * @param event the slash command interaction event
     * @param guildId the guild ID
     */
    private void handleActionViewAll(@NotNull SlashCommandInteractionEvent event, @NotNull GuildID guildId) {
        GuildPreferences prefs = PreferencesManager.getInstance().getOrDefaultPreferences(guildId);

        StringBuilder sb = new StringBuilder("**Current Moderation Actions:**\n");
        for (ActionType action : new ActionType[]{
                ActionType.WARN, ActionType.TIMEOUT, ActionType.DELETE, ActionType.KICK, ActionType.BAN
        }) {
            boolean enabled = PreferencesManager.getInstance().getActionEnabled(prefs, action);
            sb.append("• **").append(action.toString().toLowerCase()).append("**: ")
                    .append(enabled ? "✅ enabled" : "❌ disabled").append("\n");
        }

        event.reply(sb.toString()).setEphemeral(true).queue();
    }

    /**
     * Displays the enabled/disabled state of a specific moderation action.
     *
     * @param event the slash command interaction event
     * @param guildId the guild ID
     * @param actionStr the action name as provided by the user
     */
    private void handleActionViewOne(@NotNull SlashCommandInteractionEvent event, @NotNull GuildID guildId, @NotNull String actionStr) {
        ActionType actionType = ActionType.parseActionType(actionStr);
        if (actionType == null) {
            event.reply("Invalid action. Valid options are: warn, timeout, delete, kick, ban")
                    .setEphemeral(true).queue();
            return;
        }

        GuildPreferences prefs = PreferencesManager.getInstance().getOrDefaultPreferences(guildId);
        boolean enabled = PreferencesManager.getInstance().getActionEnabled(prefs, actionType);
        event.reply("The **" + actionStr + "** action is currently " + (enabled ? "**enabled**" : "**disabled**") + ".")
                .setEphemeral(true).queue();
    }

    /**
     * Updates the enabled/disabled state of a specific moderation action.
     *
     * @param event the slash command interaction event
     * @param guildId the guild ID
     * @param actionStr the action name as provided by the user
     * @param enabled the desired enabled state
     */
    private void handleActionUpdate(@NotNull SlashCommandInteractionEvent event, @NotNull GuildID guildId, @NotNull String actionStr, boolean enabled) {
        ActionType actionType = ActionType.parseActionType(actionStr);
        if (actionType == null) {
            event.reply("Invalid action. Valid options are: warn, timeout, delete, kick, ban")
                    .setEphemeral(true).queue();
            return;
        }

        GuildPreferences prefs = PreferencesManager.getInstance().getOrDefaultPreferences(guildId);
        prefs = PreferencesManager.getInstance().setActionEnabled(prefs, actionType, enabled);

        if (PreferencesManager.getInstance().updatePreferences(prefs)) {
            String status = enabled ? "enabled" : "disabled";
            event.reply("The **" + actionStr + "** action has been **" + status + "**.")
                    .setEphemeral(true).queue();
            logger.debug("Guild {} action {} set to {}", guildId.value(), actionStr, enabled);
        } else {
            event.reply(PreferencesCommands.PreferencesMessages.UPDATE_FAILED)
                    .setEphemeral(true).queue();
        }
    }

    // =========================================================================
    // Component Interaction Sub-handlers
    // =========================================================================

    /**
     * Handles the AI moderation toggle button click.
     *
     * @param event the button interaction event
     * @param guildId the guild ID
     */
    private void handleAiToggleButton(@NotNull ButtonInteractionEvent event, @NotNull GuildID guildId) {
        GuildPreferences prefs = PreferencesManager.getInstance().getOrDefaultPreferences(guildId);
        prefs = prefs.withAiEnabled(!prefs.aiEnabled());
        PreferencesManager.getInstance().updatePreferences(prefs);
        event.editMessageEmbeds(PreferencesEmbedUI.buildSettingsEmbed("actions"))
                .setComponents(PreferencesEmbedUI.buildSettingsComponents(guildId, "actions")).queue();
    }

    /**
     * Handles a moderation action toggle button click.
     *
     * @param event the button interaction event
     * @param guildId the guild ID
     * @param componentId the button component ID
     */
    private void handleActionToggleButton(@NotNull ButtonInteractionEvent event,
                                          @NotNull GuildID guildId,
                                          @NotNull String componentId) {
        String actionStr = componentId.substring("pref_action_".length());
        ActionType actionType = ActionType.parseActionType(actionStr.toLowerCase());
        if (actionType != null) {
            GuildPreferences prefs = PreferencesManager.getInstance().getOrDefaultPreferences(guildId);
            boolean enabled = PreferencesManager.getInstance().getActionEnabled(prefs, actionType);
            prefs = PreferencesManager.getInstance().setActionEnabled(prefs, actionType, !enabled);
            PreferencesManager.getInstance().updatePreferences(prefs);
        }
        event.editMessageEmbeds(PreferencesEmbedUI.buildSettingsEmbed("actions"))
                .setComponents(PreferencesEmbedUI.buildSettingsComponents(guildId, "actions")).queue();
    }

    /**
     * Handles channel selection in entity select menus.
     *
     * @param event the entity select interaction event
     * @param guildId the guild ID
     * @param componentId the select menu component ID
     */
    private void handleChannelSelection(@NotNull EntitySelectInteractionEvent event, @NotNull GuildID guildId, @NotNull String componentId) {
        long channelId = event.getValues().getFirst().getIdLong();
        GuildPreferences prefs = PreferencesManager.getInstance().getOrDefaultPreferences(guildId);

        if (componentId.equals("pref_rules_channel")) {
            prefs = prefs.withRulesChannelId(channelId);
        } else if (componentId.equals("pref_audit_channel")) {
            prefs = prefs.withAuditLogChannelId(channelId);
        }

        PreferencesManager.getInstance().updatePreferences(prefs);
    }

    // =========================================================================
    // Basic Setting Sub-handlers
    // =========================================================================

    /**
     * Reports the current AI moderation status.
     *
     * @param event the slash command interaction event
     * @param guildId the guild ID
     */
    private void reportAiStatus(@NotNull SlashCommandInteractionEvent event, @NotNull GuildID guildId) {
        GuildPreferences prefs = PreferencesManager.getInstance().getOrDefaultPreferences(guildId);
        String status = prefs.aiEnabled() ? "**enabled**" : "**disabled**";
        event.reply("AI moderation is currently " + status + " for this guild.")
                .setEphemeral(true).queue();
    }

    /**
     * Updates the AI moderation status for a guild.
     *
     * @param event the slash command interaction event
     * @param guildId the guild ID
     * @param enabled the desired enabled state
     */
    private void updateAiStatus(@NotNull SlashCommandInteractionEvent event, @NotNull GuildID guildId, boolean enabled) {
        GuildPreferences prefs = PreferencesManager.getInstance()
                .getOrDefaultPreferences(guildId)
                .withAiEnabled(enabled);

        if (PreferencesManager.getInstance().updatePreferences(prefs)) {
            String status = enabled ? "enabled" : "disabled";
            event.reply("AI moderation has been **" + status + "** for this guild.")
                    .setEphemeral(true).queue();
            logger.debug("Guild {} AI moderation set to {}", guildId.value(), enabled);
        } else {
            event.reply(PreferencesCommands.PreferencesMessages.UPDATE_FAILED)
                    .setEphemeral(true).queue();
        }
    }

    /**
     * Updates the rules channel for a guild.
     *
     * @param event the slash command interaction event
     * @param guildId the guild ID
     * @param channel the new rules channel
     */
    private void updateRulesChannel(@NotNull SlashCommandInteractionEvent event, @NotNull GuildID guildId, @NotNull GuildChannel channel) {
        GuildPreferences prefs = PreferencesManager.getInstance()
                .getOrDefaultPreferences(guildId)
                .withRulesChannelId(new ChannelID(channel.getIdLong()));

        if (PreferencesManager.getInstance().updatePreferences(prefs)) {
            event.reply("Rules channel has been set to " + channel.getAsMention())
                    .setEphemeral(true).queue();
            logger.debug("Guild {} rules channel set to {}", guildId.value(), channel.getId());
        } else {
            event.reply(PreferencesCommands.PreferencesMessages.UPDATE_FAILED)
                    .setEphemeral(true).queue();
        }
    }

    /**
     * Updates the audit log channel for a guild.
     *
     * @param event the slash command interaction event
     * @param guildId the guild ID
     * @param channel the new audit log channel
     */
    private void updateAuditChannel(@NotNull SlashCommandInteractionEvent event, @NotNull GuildID guildId, @NotNull GuildChannel channel) {
        GuildPreferences prefs = PreferencesManager.getInstance()
                .getOrDefaultPreferences(guildId)
                .withAuditLogChannelId(new ChannelID(channel.getIdLong()));

        if (PreferencesManager.getInstance().updatePreferences(prefs)) {
            event.reply("Audit log channel has been set to " + channel.getAsMention())
                    .setEphemeral(true).queue();
            logger.debug("Guild {} audit log channel set to {}", guildId.value(), channel.getId());
        } else {
            event.reply(PreferencesCommands.PreferencesMessages.UPDATE_FAILED)
                    .setEphemeral(true).queue();
        }
    }

    // =========================================================================
    // Display Helpers
    // =========================================================================

    /**
     * Replies with the current channel for a given preference.
     *
     * <p>Handles edge cases such as a configured channel that has been deleted
     * from the guild, gracefully informing the user.</p>
     *
     * @param event the slash command interaction event
     * @param guild the guild where the command was invoked
     * @param channelId the configured channel ID (may be {@code null})
     * @param channelType human-readable label, e.g. {@code "Rules channel"}
     */
    private void displayCurrentChannel(@NotNull SlashCommandInteractionEvent event, @NotNull Guild guild, @Nullable ChannelID channelId, @NotNull String channelType) {
        if (channelId == null) {
            event.reply("No " + channelType + " is currently configured.").setEphemeral(true).queue();
            return;
        }

        GuildChannel channel = guild.getGuildChannelById(channelId.value());
        if (channel != null) {
            event.reply(channelType + " is currently set to " + channel.getAsMention())
                    .setEphemeral(true).queue();
        } else {
            event.reply(channelType + " is configured but no longer exists (ID: `" + channelId.value() + "`)")
                    .setEphemeral(true).queue();
        }
    }
}