package net.honeyberries.discord.slashCommands;

import net.dv8tion.jda.api.Permission;
import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.Member;
import net.dv8tion.jda.api.events.interaction.command.SlashCommandInteractionEvent;
import net.dv8tion.jda.api.hooks.ListenerAdapter;
import net.dv8tion.jda.api.interactions.commands.OptionMapping;
import net.dv8tion.jda.api.interactions.commands.OptionType;
import net.dv8tion.jda.api.interactions.commands.build.Commands;
import net.dv8tion.jda.api.interactions.commands.build.OptionData;
import net.dv8tion.jda.api.interactions.commands.build.SlashCommandData;
import net.dv8tion.jda.api.interactions.commands.build.SubcommandData;
import net.dv8tion.jda.api.requests.restaction.CommandListUpdateAction;
import net.honeyberries.database.GuildPreferencesRepository;
import net.honeyberries.database.SpecialUsersRepository;
import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.preferences.GuildPreferences;
import org.jetbrains.annotations.NotNull;
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
    private final GuildPreferencesRepository preferencesRepo = GuildPreferencesRepository.getInstance();
    private final SpecialUsersRepository specialUsersRepo = SpecialUsersRepository.getInstance();

    /**
     * Registers the preferences command and its subcommands with the Discord bot.
     *
     * @param commands the command list update action to register commands with. Must not be null.
     * @throws NullPointerException if commands is null
     */
    public void registerPreferencesCommands(@NotNull CommandListUpdateAction commands) {
        Objects.requireNonNull(commands, "commands must not be null");

        SubcommandData enableAiSub = new SubcommandData(
                "enable_ai",
                "Enable or disable AI moderation"
        ).addOptions(
                new OptionData(OptionType.BOOLEAN, "enabled", "Enable or disable AI", true)
        );

        SubcommandData setRulesChannelSub = new SubcommandData(
                "set_rules_channel",
                "Set the rules channel for this guild"
        ).addOptions(
                new OptionData(OptionType.CHANNEL, "channel", "Channel for rules", true)
        );

        SubcommandData setAuditChannelSub = new SubcommandData(
                "set_audit_channel",
                "Set the audit log channel for this guild"
        ).addOptions(
                new OptionData(OptionType.CHANNEL, "channel", "Channel for audit logs", true)
        );

        SubcommandData settingsSub = new SubcommandData(
                "settings",
                "View and manage guild preferences with a graphical interface"
        );

        SlashCommandData preferencesCommand = Commands.slash(
                "preferences",
                "Manage guild preferences and settings"
        ).addSubcommands(enableAiSub, setRulesChannelSub, setAuditChannelSub, settingsSub);

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

        Guild guild = event.getGuild();
        if (guild == null) {
            event.reply("This command can only be used in servers!").setEphemeral(true).queue();
            return;
        }

        Member member = event.getMember();
        if (member == null || (!member.hasPermission(Permission.MANAGE_SERVER)
                && !specialUsersRepo.isSpecialUser(event.getUser()))) {
            event.reply("You need the **Manage Server** permission or higher to use this command.").setEphemeral(true).queue();
            return;
        }

        String subcommand = event.getSubcommandName();
        if (subcommand == null) {
            event.reply("Please specify a subcommand.").setEphemeral(true).queue();
            return;
        }

        try {
            switch (subcommand) {
                case "enable_ai" -> handleEnableAi(event);
                case "set_rules_channel" -> handleSetRulesChannel(event);
                case "set_audit_channel" -> handleSetAuditChannel(event);
                case "settings" -> handleSettings(event);
                default -> event.reply("Unknown subcommand").setEphemeral(true).queue();
            }
        } catch (Exception e) {
            logger.error("Error handling /preferences {}", subcommand, e);
            event.reply("An unexpected error occurred while processing the command.").setEphemeral(true).queue();
        }
    }

    /**
     * Handles the enable_ai subcommand.
     *
     * <p>Enables or disables AI moderation for the guild and persists the change
     * to the database. Sends confirmation via ephemeral reply.
     *
     * @param event the slash command interaction event. Must not be null.
     * @throws NullPointerException if event is null
     */
    private void handleEnableAi(@NotNull SlashCommandInteractionEvent event) {
        Objects.requireNonNull(event, "event must not be null");
        try {
            Guild guild = Objects.requireNonNull(event.getGuild());
            GuildID guildId = new GuildID(guild.getIdLong());

            Boolean enabled = event.getOption("enabled", OptionMapping::getAsBoolean);
            if (enabled == null) {
                event.reply("Please specify true or false.").setEphemeral(true).queue();
                return;
            }

            GuildPreferences currentPrefs = preferencesRepo.getGuildPreferences(guildId);
            GuildPreferences updatedPrefs = currentPrefs != null
                    ? currentPrefs.withAiEnabled(enabled)
                    : new GuildPreferences.Builder(guildId).aiEnabled(enabled).build();

            boolean success = preferencesRepo.addOrUpdateGuildPreferences(updatedPrefs);
            if (success) {
                String status = enabled ? "enabled" : "disabled";
                event.reply("AI moderation has been " + status + " for this guild.").setEphemeral(true).queue();
                logger.debug("Set AI enabled to {} for guild {}", enabled, guildId.value());
            } else {
                event.reply("Failed to update preference. Please try again.").setEphemeral(true).queue();
            }
        } catch (Exception e) {
            logger.error("Error handling enable_ai subcommand", e);
            event.reply("Failed to update preference.").setEphemeral(true).queue();
        }
    }

    /**
     * Handles the set_rules_channel subcommand.
     *
     * <p>Sets the rules channel for the guild and persists the change to the database.
     * Sends confirmation via ephemeral reply.
     *
     * @param event the slash command interaction event. Must not be null.
     * @throws NullPointerException if event is null
     */
    private void handleSetRulesChannel(@NotNull SlashCommandInteractionEvent event) {
        Objects.requireNonNull(event, "event must not be null");
        try {
            Guild guild = Objects.requireNonNull(event.getGuild());
            GuildID guildId = new GuildID(guild.getIdLong());

            net.dv8tion.jda.api.entities.channel.middleman.GuildChannel channel =
                    event.getOption("channel", null, OptionMapping::getAsChannel);

            if (channel == null) {
                event.reply("Please specify a valid channel.").setEphemeral(true).queue();
                return;
            }

            ChannelID channelId = new ChannelID(channel.getIdLong());
            GuildPreferences currentPrefs = preferencesRepo.getGuildPreferences(guildId);
            GuildPreferences updatedPrefs = currentPrefs != null
                    ? currentPrefs.withRulesChannelId(channelId)
                    : new GuildPreferences.Builder(guildId).rulesChannelId(channelId).build();

            boolean success = preferencesRepo.addOrUpdateGuildPreferences(updatedPrefs);
            if (success) {
                event.reply("Rules channel has been set to " + channel.getAsMention()).setEphemeral(true).queue();
                logger.debug("Set rules channel to {} for guild {}", channel.getId(), guildId.value());
            } else {
                event.reply("Failed to update preference. Please try again.").setEphemeral(true).queue();
            }
        } catch (Exception e) {
            logger.error("Error handling set_rules_channel subcommand", e);
            event.reply("Failed to update preference.").setEphemeral(true).queue();
        }
    }

    /**
     * Handles the set_audit_channel subcommand.
     *
     * <p>Sets the audit log channel for the guild and persists the change to the database.
     * Sends confirmation via ephemeral reply.
     *
     * @param event the slash command interaction event. Must not be null.
     * @throws NullPointerException if event is null
     */
    private void handleSetAuditChannel(@NotNull SlashCommandInteractionEvent event) {
        Objects.requireNonNull(event, "event must not be null");
        try {
            Guild guild = Objects.requireNonNull(event.getGuild());
            GuildID guildId = new GuildID(guild.getIdLong());

            net.dv8tion.jda.api.entities.channel.middleman.GuildChannel channel =
                    event.getOption("channel", null, OptionMapping::getAsChannel);

            if (channel == null) {
                event.reply("Please specify a valid channel.").setEphemeral(true).queue();
                return;
            }

            ChannelID channelId = new ChannelID(channel.getIdLong());
            GuildPreferences currentPrefs = preferencesRepo.getGuildPreferences(guildId);
            GuildPreferences updatedPrefs = currentPrefs != null
                    ? currentPrefs.withAuditLogChannelId(channelId)
                    : new GuildPreferences.Builder(guildId).auditLogChannelId(channelId).build();

            boolean success = preferencesRepo.addOrUpdateGuildPreferences(updatedPrefs);
            if (success) {
                event.reply("Audit log channel has been set to " + channel.getAsMention()).setEphemeral(true).queue();
                logger.debug("Set audit channel to {} for guild {}", channel.getId(), guildId.value());
            } else {
                event.reply("Failed to update preference. Please try again.").setEphemeral(true).queue();
            }
        } catch (Exception e) {
            logger.error("Error handling set_audit_channel subcommand", e);
            event.reply("Failed to update preference.").setEphemeral(true).queue();
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
}
