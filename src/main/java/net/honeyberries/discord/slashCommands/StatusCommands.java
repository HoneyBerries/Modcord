package net.honeyberries.discord.slashCommands;

import net.dv8tion.jda.api.JDA;
import net.dv8tion.jda.api.events.interaction.command.SlashCommandInteractionEvent;
import net.dv8tion.jda.api.hooks.ListenerAdapter;
import net.dv8tion.jda.api.interactions.commands.build.Commands;
import net.dv8tion.jda.api.interactions.commands.build.SubcommandData;
import net.dv8tion.jda.api.requests.restaction.CommandListUpdateAction;
import net.honeyberries.database.Database;
import org.jetbrains.annotations.NotNull;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class StatusCommands extends ListenerAdapter {

    private static final Logger logger = LoggerFactory.getLogger(StatusCommands.class);
    private final long startTime;

    public StatusCommands() {
        this.startTime = System.currentTimeMillis();
    }

    public void registerStatusCommands(CommandListUpdateAction commands) {
        try {
            commands.addCommands(
                Commands.slash("status", "Check the bot's status")
                        .addSubcommands(
                            new SubcommandData("health", "Checks if the bot is healthy"),
                            new SubcommandData("ping", "Checks the bot's ping"),
                            new SubcommandData("uptime", "Checks the bot's uptime")
                        )
            );
            logger.info("Registered /status with subcommands: health, ping, uptime");
        } catch (Exception e) {
            logger.error("Failed to register status commands", e);
            throw new RuntimeException(e);
        }
    }

    @Override
    public void onSlashCommandInteraction(@NotNull SlashCommandInteractionEvent event) {
        if (!event.getName().equals("status")) return;

        if (!event.isFromGuild()) {
            event.reply("This command can only be used in servers!").setEphemeral(true).queue();
            return;
        }

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
                default -> event.reply("Unknown subcommand").setEphemeral(true).queue();
            }
        } catch (Exception e) {
            logger.error("Error processing /status command: {}", event.getSubcommandName(), e);
            event.reply("An error occurred while processing your command").setEphemeral(true).queue();
        }
    }

    private void handleHealthCommand(SlashCommandInteractionEvent event) {
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

    private void handlePingCommand(SlashCommandInteractionEvent event) {
        long ping = event.getJDA().getGatewayPing();
        String pingMessage = String.format(":ping_pong:  Pong! Gateway ping: %dms", ping);
        event.reply(pingMessage).setEphemeral(true).queue();
    }

    private void handleUptimeCommand(SlashCommandInteractionEvent event) {
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
}