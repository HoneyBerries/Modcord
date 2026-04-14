package net.honeyberries.discord.slashCommands;

import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.events.interaction.command.SlashCommandInteractionEvent;
import net.dv8tion.jda.api.hooks.ListenerAdapter;
import net.dv8tion.jda.api.interactions.commands.OptionType;
import net.dv8tion.jda.api.interactions.commands.build.Commands;
import net.dv8tion.jda.api.interactions.commands.build.OptionData;
import net.dv8tion.jda.api.interactions.commands.build.SlashCommandData;
import net.dv8tion.jda.api.interactions.commands.build.SubcommandData;
import net.dv8tion.jda.api.requests.restaction.CommandListUpdateAction;
import net.honeyberries.util.PreferenceCommandHelper;
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
 *
 * <p>This class is a thin JDA listener — all business logic lives in
 * {@link PreferenceCommandHelper}.
 */
public class PreferencesCommands extends ListenerAdapter {

    private static final Logger logger = LoggerFactory.getLogger(PreferencesCommands.class);

    private final PreferenceCommandHelper helper = new PreferenceCommandHelper();

    /**
     * User-facing error/status messages used across the preferences command surface.
     */
    public static final class PreferencesMessages {
        public static final String UPDATE_FAILED = "Failed to update preference. Please try again.";
        public static final String RESET_FAILED  = "Failed to reset preferences. Please try again.";

        private PreferencesMessages() {}
    }

    /**
     * Registers the {@code /preferences} slash command with all its subcommands.
     *
     * @param commands the {@link CommandListUpdateAction} to register onto; must not be null
     * @throws NullPointerException if {@code commands} is null
     */
    public void registerPreferencesCommands(@NotNull CommandListUpdateAction commands) {
        Objects.requireNonNull(commands, "commands must not be null");

        SubcommandData enableAiSub = new SubcommandData(
                "enable_ai",
                "Enable or disable AI moderation (or view current setting)"
        ).addOptions(
                new OptionData(OptionType.BOOLEAN, "enabled",
                        "Enable or disable AI (leave empty to view current)", false)
        );

        SubcommandData setRulesChannelSub = new SubcommandData(
                "set_rules_channel",
                "Set the rules channel for this guild (or view current channel)"
        ).addOptions(
                new OptionData(OptionType.CHANNEL, "channel",
                        "Channel for rules (leave empty to view current)", false)
        );

        SubcommandData setAuditChannelSub = new SubcommandData(
                "set_audit_channel",
                "Set the audit log channel for this guild (or view current channel)"
        ).addOptions(
                new OptionData(OptionType.CHANNEL, "channel",
                        "Channel for audit logs (leave empty to view current)", false)
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
                new OptionData(OptionType.STRING, "action",
                        "The moderation action to toggle (leave empty to view all)", false)
                        .addChoice("warn",    "warn")
                        .addChoice("timeout", "timeout")
                        .addChoice("delete",  "delete")
                        .addChoice("kick",    "kick")
                        .addChoice("ban",     "ban"),
                new OptionData(OptionType.BOOLEAN, "enabled",
                        "Enable or disable this action (leave empty to view current)", false)
        );

        SlashCommandData preferencesCommand = Commands.slash(
                "preferences",
                "Manage guild preferences and settings"
        ).addSubcommands(
                enableAiSub, setRulesChannelSub, setAuditChannelSub,
                settingsSub, resetSub, actionSub
        );

        commands.addCommands(preferencesCommand);
        logger.info("Registered /preferences command with subcommands");
    }

    /**
     * Routes {@code /preferences} subcommand interactions to {@link PreferenceCommandHelper}.
     *
     * @param event the slash command interaction event; must not be null
     */
    @Override
    public void onSlashCommandInteraction(@NotNull SlashCommandInteractionEvent event) {
        Objects.requireNonNull(event, "event must not be null");
        if (!event.getName().equals("preferences")) {
            return;
        }

        Guild guild = helper.validateGuildAndPermissions(event);
        if (guild == null) {
            return; // helper already replied
        }

        String subcommand = event.getSubcommandName();
        if (subcommand == null) {
            event.reply("Please specify a subcommand.").setEphemeral(true).queue();
            return;
        }

        try {
            switch (subcommand) {
                case "enable_ai"         -> helper.handleEnableAi(event, guild);
                case "set_rules_channel" -> helper.handleSetRulesChannel(event, guild);
                case "set_audit_channel" -> helper.handleSetAuditChannel(event, guild);
                case "settings"          -> helper.handleSettings(event);
                case "reset"             -> helper.handleReset(event, guild);
                case "action"            -> helper.handleAction(event, guild);
                default                  -> event.reply("Unknown subcommand.").setEphemeral(true).queue();
            }
        } catch (Exception e) {
            logger.error("Error handling /preferences {}", subcommand, e);
            event.reply("An unexpected error occurred while processing the command.")
                    .setEphemeral(true).queue();
        }
    }
}