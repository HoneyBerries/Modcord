package net.honeyberries.discord.slashCommands;

import net.dv8tion.jda.api.JDA;
import net.dv8tion.jda.api.events.interaction.command.SlashCommandInteractionEvent;
import net.dv8tion.jda.api.hooks.ListenerAdapter;
import net.dv8tion.jda.api.interactions.commands.build.Commands;
import net.dv8tion.jda.api.interactions.commands.build.SlashCommandData;
import net.dv8tion.jda.api.interactions.commands.build.SubcommandData;
import net.dv8tion.jda.api.requests.restaction.CommandListUpdateAction;
import net.honeyberries.database.Database;
import org.jetbrains.annotations.NotNull;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.Objects;

/**
 * Slash command handler for bot health and status monitoring.
 *
 * <p>Provides administrators and users with real-time information about the bot's 
 * operational status including connection health, gateway ping, and uptime. Tracks 
 * bot startup time and queries database connectivity to help diagnose infrastructure 
 * issues quickly.
 */
public class StatusCommands extends ListenerAdapter {

    private static final Logger logger = LoggerFactory.getLogger(StatusCommands.class);
    private final long startTime;

    public StatusCommands() {
        this.startTime = System.currentTimeMillis();
    }

    /**
     * Registers the status command and its subcommands with the Discord bot.
     *
     * @param commands the command list update action to register commands with. Must not be null.
     * @throws NullPointerException if commands is null
     */
    public void registerStatusCommands(@NotNull CommandListUpdateAction commands) {
        Objects.requireNonNull(commands, "commands must not be null");

        SubcommandData healthSub = new SubcommandData("health", "Checks if the bot is healthy");
        SubcommandData pingSub = new SubcommandData("ping", "Checks the bot's ping");
        SubcommandData uptimeSub = new SubcommandData("uptime", "Checks the bot's uptime");
        SubcommandData guildsSub = new SubcommandData("guilds", "Shows the number of guilds the bot is in");

        SlashCommandData statusCommand = Commands.slash("status", "Bot health and status monitoring").addSubcommands(healthSub, pingSub, uptimeSub, guildsSub);

        try {
            Objects.requireNonNull(commands.addCommands(statusCommand));
            logger.info("Registered /status with subcommands: health, ping, uptime, guilds");
        } catch (Exception e) {
            logger.error("Failed to register status commands", e);
            throw new RuntimeException(e);
        }
    }

    /**
     * Handles slash command interactions for the status command.
     *
     * <p>Routes to the appropriate subcommand handler (health, ping, or uptime) 
     * after validating the event is from a guild context. All status checks are 
     * sent as ephemeral replies.
     *
     * @param event the slash command interaction event. Must not be null.
     * @throws NullPointerException if event is null
     */
    @Override
    public void onSlashCommandInteraction(@NotNull SlashCommandInteractionEvent event) {
        Objects.requireNonNull(event, "event must not be null");
        if (!event.getName().equals("status")) return;

        try {
            String subcommand = event.getSubcommandName();
            if (subcommand == null) {
                event.reply("Please specify a subcommand!").setEphemeral(true).queue();
                return;
            }

            switch (subcommand) {
                case "health" -> handleHealthCommand(event);
                case "ping" -> handlePingCommand(event);
                case "uptime" -> handleUptimeCommand(event);
                case "guilds" -> handleGuildsCommand(event);
                default -> event.reply("Unknown subcommand").setEphemeral(true).queue();
            }
        } catch (Exception e) {
            logger.error("Error processing /status command: {}", event.getSubcommandName(), e);
            event.reply("An error occurred while processing your command").setEphemeral(true).queue();
        }
    }

    /**
     * Handles the health subcommand.
     *
     * <p>Reports the bot's connection status and database health. Shows whether the 
     * bot is connected to Discord and whether the database is accessible and healthy.
     *
     * @param event the slash command interaction event. Must not be null.
     * @throws NullPointerException if event is null
     */
    private void handleHealthCommand(@NotNull SlashCommandInteractionEvent event) {
        Objects.requireNonNull(event, "event must not be null");
        StringBuilder healthStatus = new StringBuilder();

        if (event.getJDA().getStatus() != JDA.Status.CONNECTED) {
            healthStatus.append(":x:  **Bot Status:** Not Connected\n\n");
        } else {
            healthStatus.append(":robot:  **Bot Status:** Operational\n\n");
        }

        if (Database.getInstance().isHealthy()) {
            healthStatus.append(":floppy_disk:  **Database Status:** Connected & Healthy\n");
        } else {
            healthStatus.append(":x:  **Database Status:** Broken or Unreachable\n");
        }

        event.reply(healthStatus.toString()).setEphemeral(true).queue();
    }

    /**
     * Handles the ping subcommand.
     *
     * <p>Reports the gateway ping (latency) between the bot and Discord's servers. 
     * Lower values indicate better connectivity.
     *
     * @param event the slash command interaction event. Must not be null.
     * @throws NullPointerException if event is null
     */
    private void handlePingCommand(@NotNull SlashCommandInteractionEvent event) {
        Objects.requireNonNull(event, "event must not be null");
        long ping = event.getJDA().getGatewayPing();
        String pingMessage = String.format(":ping_pong:  Pong! Gateway ping: %dms", ping);
        event.reply(pingMessage).setEphemeral(true).queue();
    }

    /**
     * Handles the uptime subcommand.
     *
     * <p>Calculates and reports how long the bot has been running since last startup. 
     * Displays uptime in weeks, days, hours, minutes, and seconds.
     *
     * @param event the slash command interaction event. Must not be null.
     * @throws NullPointerException if event is null
     */
    private void handleUptimeCommand(@NotNull SlashCommandInteractionEvent event) {
        Objects.requireNonNull(event, "event must not be null");
        long uptimeMillis = System.currentTimeMillis() - startTime;
        long weeks = uptimeMillis / (1000 * 60 * 60 * 24 * 7);
        long days = (uptimeMillis / (1000 * 60 * 60 * 24)) % 7;
        long hours = (uptimeMillis / (1000 * 60 * 60)) % 24;
        long minutes = (uptimeMillis / (1000 * 60)) % 60;
        long seconds = (uptimeMillis / 1000) % 60;

        String uptimeMessage = String.format(
                ":alarm_clock:  Bot uptime: %d weeks, %d days, %d hours, %d minutes, %d seconds",
                weeks, days, hours, minutes, seconds
        );

        event.reply(uptimeMessage).setEphemeral(true).queue();
    }

    /**
     * Handles the guilds subcommand.
     *
     * <p>Reports the number of guilds the bot is currently a member of.
     *
     * @param event the slash command interaction event. Must not be null.
     * @throws NullPointerException if event is null
     */
    private void handleGuildsCommand(@NotNull SlashCommandInteractionEvent event) {
        Objects.requireNonNull(event, "event must not be null");
        int guildCount = event.getJDA().getGuilds().size();
        String guildsMessage = String.format(":globe_with_meridians:  Bot is in **%d** guild(s)", guildCount);
        event.reply(guildsMessage).setEphemeral(true).queue();
    }
}