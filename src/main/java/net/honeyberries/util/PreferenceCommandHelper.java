package net.honeyberries.util;

import net.dv8tion.jda.api.Permission;
import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.Member;
import net.dv8tion.jda.api.entities.channel.middleman.GuildChannel;
import net.dv8tion.jda.api.events.interaction.command.SlashCommandInteractionEvent;
import net.dv8tion.jda.api.interactions.commands.OptionMapping;
import net.honeyberries.database.SpecialUsersRepository;
import net.honeyberries.datatypes.action.ActionType;
import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.preferences.GuildPreferences;
import net.honeyberries.discord.slashCommands.PreferencesCommands;
import net.honeyberries.preferences.PreferencesManager;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.Objects;

/**
 * Business-logic helper for the {@code /preferences} slash command.
 *
 * <p>All methods are package-private so that {@link PreferencesCommands} (same package
 * boundary via delegation) can call them while keeping them out of the wider public API.
 */
public class PreferenceCommandHelper {

    private final SpecialUsersRepository specialUsersRepo = SpecialUsersRepository.getInstance();
    private final Logger logger = LoggerFactory.getLogger(PreferenceCommandHelper.class);

    // -------------------------------------------------------------------------
    // Permission guard
    // -------------------------------------------------------------------------

    /**
     * Validates that the event originates from a guild and that the invoker holds
     * {@link Permission#MANAGE_SERVER} or is a special user.
     *
     * @param event the slash command interaction event
     * @return the {@link Guild} if validation passes, or {@code null} if it fails
     *         (the user has already been notified via an ephemeral reply)
     */
    @Nullable
    public Guild validateGuildAndPermissions(@NotNull SlashCommandInteractionEvent event) {
        Guild guild = event.getGuild();
        if (guild == null) {
            event.reply("This command can only be used in servers!").setEphemeral(true).queue();
            return null;
        }

        Member member = event.getMember();
        if (member == null
                || (!member.hasPermission(Permission.MANAGE_SERVER)
                && !specialUsersRepo.isSpecialUser(event.getUser()))) {
            event.reply("You need the **Manage Server** permission or higher to use this command.")
                    .setEphemeral(true).queue();
            return null;
        }

        return guild;
    }

    // -------------------------------------------------------------------------
    // Subcommand handlers
    // -------------------------------------------------------------------------

    /**
     * Handles {@code /preferences enable_ai}.
     *
     * <p>Enables or disables AI moderation for the guild. If {@code enabled} is omitted,
     * reports the current setting instead.
     */
    public void handleEnableAi(@NotNull SlashCommandInteractionEvent event, @NotNull Guild guild) {
        Objects.requireNonNull(event, "event must not be null");
        Objects.requireNonNull(guild, "guild must not be null");
        try {
            GuildID guildId = GuildID.fromGuild(guild);
            Boolean enabled = event.getOption("enabled", OptionMapping::getAsBoolean);

            if (enabled == null) {
                GuildPreferences guildPreferences = PreferencesManager.getInstance().getOrDefaultPreferences(guildId);
                String status = guildPreferences.aiEnabled() ? "**enabled**" : "**disabled**";
                event.reply("AI moderation is currently " + status + " for this guild.")
                        .setEphemeral(true).queue();
                return;
            }

            GuildPreferences guildPreferences = PreferencesManager.getInstance()
                    .getOrDefaultPreferences(guildId)
                    .withAiEnabled(enabled);

            if (PreferencesManager.getInstance().updatePreferences(guildPreferences)) {
                String status = enabled ? "enabled" : "disabled";
                event.reply("AI moderation has been **" + status + "** for this guild.")
                        .setEphemeral(true).queue();
                logger.debug("Guild {} AI moderation set to {}", guildId.value(), enabled);
            } else {
                event.reply(PreferencesCommands.PreferencesMessages.UPDATE_FAILED)
                        .setEphemeral(true).queue();
            }
        } catch (Exception e) {
            logger.error("Error handling enable_ai subcommand", e);
            event.reply(PreferencesCommands.PreferencesMessages.UPDATE_FAILED).setEphemeral(true).queue();
        }
    }

    /**
     * Handles {@code /preferences set_rules_channel}.
     *
     * <p>Sets the rules channel for the guild. If {@code channel} is omitted,
     * reports the currently configured channel instead.
     */
    public void handleSetRulesChannel(@NotNull SlashCommandInteractionEvent event, @NotNull Guild guild) {
        Objects.requireNonNull(event, "event must not be null");
        Objects.requireNonNull(guild, "guild must not be null");
        try {
            GuildID guildId = GuildID.fromGuild(guild);
            GuildChannel channel = event.getOption("channel", null, OptionMapping::getAsChannel);

            if (channel == null) {
                GuildPreferences guildPreferences = PreferencesManager.getInstance().getOrDefaultPreferences(guildId);
                displayCurrentChannel(event, guild, guildPreferences.rulesChannelID(), "Rules channel");
                return;
            }

            GuildPreferences guildPreferences = PreferencesManager.getInstance()
                    .getOrDefaultPreferences(guildId)
                    .withRulesChannelId(new ChannelID(channel.getIdLong()));

            if (PreferencesManager.getInstance().updatePreferences(guildPreferences)) {
                event.reply("Rules channel has been set to " + channel.getAsMention())
                        .setEphemeral(true).queue();
                logger.debug("Guild {} rules channel set to {}", guildId.value(), channel.getId());
            } else {
                event.reply(PreferencesCommands.PreferencesMessages.UPDATE_FAILED)
                        .setEphemeral(true).queue();
            }
        } catch (Exception e) {
            logger.error("Error handling set_rules_channel subcommand", e);
            event.reply(PreferencesCommands.PreferencesMessages.UPDATE_FAILED).setEphemeral(true).queue();
        }
    }

    /**
     * Handles {@code /preferences set_audit_channel}.
     *
     * <p>Sets the audit-log channel for the guild. If {@code channel} is omitted,
     * reports the currently configured channel instead.
     */
    public void handleSetAuditChannel(@NotNull SlashCommandInteractionEvent event, @NotNull Guild guild) {
        Objects.requireNonNull(event, "event must not be null");
        Objects.requireNonNull(guild, "guild must not be null");
        try {
            GuildID guildId = GuildID.fromGuild(guild);
            GuildChannel channel = event.getOption("channel", null, OptionMapping::getAsChannel);

            if (channel == null) {
                GuildPreferences guildPreferences = PreferencesManager.getInstance().getOrDefaultPreferences(guildId);
                displayCurrentChannel(event, guild, guildPreferences.auditLogChannelId(), "Audit log channel");
                return;
            }

            GuildPreferences guildPreferences = PreferencesManager.getInstance()
                    .getOrDefaultPreferences(guildId)
                    .withAuditLogChannelId(new ChannelID(channel.getIdLong()));

            if (PreferencesManager.getInstance().updatePreferences(guildPreferences)) {
                event.reply("Audit log channel has been set to " + channel.getAsMention())
                        .setEphemeral(true).queue();
                logger.debug("Guild {} audit log channel set to {}", guildId.value(), channel.getId());
            } else {
                event.reply(PreferencesCommands.PreferencesMessages.UPDATE_FAILED)
                        .setEphemeral(true).queue();
            }
        } catch (Exception e) {
            logger.error("Error handling set_audit_channel subcommand", e);
            event.reply(PreferencesCommands.PreferencesMessages.UPDATE_FAILED).setEphemeral(true).queue();
        }
    }

    /**
     * Handles {@code /preferences settings}.
     *
     * <p>TODO: implement a component-based settings GUI.
     */
    public void handleSettings(@NotNull SlashCommandInteractionEvent event) {
        Objects.requireNonNull(event, "event must not be null");
        event.reply("Settings GUI is not yet implemented.").setEphemeral(true).queue();
    }

    /**
     * Handles {@code /preferences reset}.
     *
     * <p>Resets all guild preferences to their default values.
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

    /**
     * Handles {@code /preferences action}.
     *
     * <p>Routes to a focused sub-handler based on which options were supplied:
     * <ul>
     *   <li>Neither {@code action} nor {@code enabled}: show all actions and their states.</li>
     *   <li>{@code action} only: show that action's current state.</li>
     *   <li>Both provided: update the action's enabled state.</li>
     * </ul>
     */
    public void handleAction(@NotNull SlashCommandInteractionEvent event, @NotNull Guild guild) {
        Objects.requireNonNull(event, "event must not be null");
        Objects.requireNonNull(guild, "guild must not be null");
        try {
            GuildID guildId = GuildID.fromGuild(guild);
            String actionStr = event.getOption("action", OptionMapping::getAsString);
            Boolean enabled  = event.getOption("enabled", OptionMapping::getAsBoolean);

            if (actionStr == null && enabled == null) {
                handleActionViewAll(event, guildId);
            } else if (actionStr != null && enabled == null) {
                handleActionViewOne(event, guildId, actionStr);
            } else if (actionStr != null) {
                handleActionUpdate(event, guildId, actionStr, enabled);
            } else {
                // enabled provided but no action — ask for the action
                event.reply("Please specify an action to enable or disable.").setEphemeral(true).queue();
            }
        } catch (Exception e) {
            logger.error("Error handling action subcommand", e);
            event.reply(PreferencesCommands.PreferencesMessages.UPDATE_FAILED).setEphemeral(true).queue();
        }
    }

    // -------------------------------------------------------------------------
    // Action sub-handlers
    // -------------------------------------------------------------------------

    private void handleActionViewAll(@NotNull SlashCommandInteractionEvent event, @NotNull GuildID guildId) {
        GuildPreferences guildPreferences = PreferencesManager.getInstance().getOrDefaultPreferences(guildId);

        StringBuilder sb = new StringBuilder("**Current Moderation Actions:**\n");
        for (ActionType action : new ActionType[]{
                ActionType.WARN, ActionType.TIMEOUT, ActionType.DELETE, ActionType.KICK, ActionType.BAN
        }) {
            boolean on = PreferencesManager.getInstance().getActionEnabled(guildPreferences, action);
            sb.append("• **").append(action.toString().toLowerCase()).append("**: ")
                    .append(on ? "✅ enabled" : "❌ disabled").append("\n");
        }

        event.reply(sb.toString()).setEphemeral(true).queue();
    }

    private void handleActionViewOne(
            @NotNull SlashCommandInteractionEvent event,
            @NotNull GuildID guildId,
            @NotNull String actionStr) {

        ActionType actionType = ActionType.parseActionType(actionStr);
        if (actionType == null) {
            event.reply("Invalid action. Valid options are: warn, timeout, delete, kick, ban")
                    .setEphemeral(true).queue();
            return;
        }

        GuildPreferences guildPreferences = PreferencesManager.getInstance().getOrDefaultPreferences(guildId);
        boolean on = PreferencesManager.getInstance().getActionEnabled(guildPreferences, actionType);
        event.reply("The **" + actionStr + "** action is currently " + (on ? "**enabled**" : "**disabled**") + ".")
                .setEphemeral(true).queue();
    }

    private void handleActionUpdate(
            @NotNull SlashCommandInteractionEvent event,
            @NotNull GuildID guildId,
            @NotNull String actionStr,
            boolean enabled) {

        ActionType actionType = ActionType.parseActionType(actionStr);
        if (actionType == null) {
            event.reply("Invalid action. Valid options are: warn, timeout, delete, kick, ban")
                    .setEphemeral(true).queue();
            return;
        }

        GuildPreferences guildPreferences = PreferencesManager.getInstance().getOrDefaultPreferences(guildId);
        guildPreferences = PreferencesManager.getInstance().setActionEnabled(guildPreferences, actionType, enabled);

        if (PreferencesManager.getInstance().updatePreferences(guildPreferences)) {
            String status = enabled ? "enabled" : "disabled";
            event.reply("The **" + actionStr + "** action has been **" + status + "**.")
                    .setEphemeral(true).queue();
            logger.debug("Guild {} action {} set to {}", guildId.value(), actionStr, enabled);
        } else {
            event.reply(PreferencesCommands.PreferencesMessages.UPDATE_FAILED).setEphemeral(true).queue();
        }
    }

    // -------------------------------------------------------------------------
    // Shared display helpers
    // -------------------------------------------------------------------------

    /**
     * Replies with the current channel for a given preference, handling the
     * "configured but deleted" edge case gracefully.
     *
     * @param channelType human-readable label, e.g. {@code "Rules channel"}
     */
    private void displayCurrentChannel(
            @NotNull SlashCommandInteractionEvent event,
            @NotNull Guild guild,
            @Nullable ChannelID channelId,
            @NotNull String channelType) {

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