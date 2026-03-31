package net.honeyberries;


import net.dv8tion.jda.api.JDA;
import net.dv8tion.jda.api.JDABuilder;
import net.dv8tion.jda.api.entities.Activity;
import net.dv8tion.jda.api.requests.GatewayIntent;
import net.dv8tion.jda.api.requests.restaction.CommandListUpdateAction;
import net.honeyberries.config.AppConfig;
import net.honeyberries.database.Database;
import net.honeyberries.discord.slashCommands.DebugCommands;
import net.honeyberries.discord.slashCommands.StatusCommands;
import net.honeyberries.discord.listener.MessageListener;
import net.honeyberries.task.ChannelGuidelinesTask;
import net.honeyberries.task.GuildRulesTask;
import net.honeyberries.task.UnbanWatcherTask;
import net.honeyberries.util.JDAManager;
import net.honeyberries.util.TokenManager;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import java.nio.file.Paths;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

public class Main {

    private final Logger logger = LoggerFactory.getLogger(Main.class);
    private JDA discordBot;

    ScheduledExecutorService scheduler;

    static void main(String[] args) {
        Main main = new Main();
        try {
            main.setupDatabase();
            main.setupDiscordBot();
            main.setupTasks();
        } catch (InterruptedException e) {
            main.logger.error("Failed to set up Discord bot", e);
        } finally {
            if (args.length != 0 && args[0].equalsIgnoreCase("--test")) {
                Thread.startVirtualThread(() -> {
                    try {
                        Thread.sleep(5000); // Wait for 5 seconds before shutting down
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                    }
                    main.shutdown();
                });
            }

        }
    }

    private void setupDatabase() {
        logger.info("Initializing database");
        // Load configuration from app_config.yml
        AppConfig config = new AppConfig(Paths.get("./config/app_config.yml"));
        
        Database.getInstance().initialize(config);
        logger.info("Database initialized successfully");
    }

    private void setupDiscordBot() throws InterruptedException {
        logger.info("Creating Discord bot instance");
        Activity activity = Activity.watching("your server while you sleep");
        discordBot = JDABuilder.createDefault(TokenManager.getDiscordBotToken(),
                GatewayIntent.getIntents(GatewayIntent.ALL_INTENTS)
        ).setActivity(activity)
        .build();

        discordBot.awaitReady();
        
        // Store JDA instance for global access
        JDAManager.getInstance().setJDA(discordBot);

        logger.info("Discord bot is connected as {}", discordBot.getSelfUser().getName());

        // 1. Create ONE single update action
        CommandListUpdateAction commands = discordBot.updateCommands();

        // Register event listeners
        MessageListener messageListener = new MessageListener();
        discordBot.addEventListener(messageListener);

        // 2. Pass the shared 'commands' action to each registration method
        StatusCommands statusCommands = new StatusCommands();
        discordBot.addEventListener(statusCommands);
        statusCommands.registerStatusCommands(commands); // Changed this
        logger.info("Added StatusCommands to queue");

        DebugCommands debugCommands = new DebugCommands();
        discordBot.addEventListener(debugCommands);
        debugCommands.registerDebugCommands(commands);
        logger.info("Added DebugCommands to queue");

        // 3. Finally, queue them all at once
        commands.queue();
        logger.info("All slash commands synced with Discord successfully");

        logger.info("Discord bot setup complete");
    }


    private void setupTasks() {
        scheduler = Executors.newScheduledThreadPool(8);

        scheduler.scheduleAtFixedRate(new UnbanWatcherTask(), 0, 1, TimeUnit.SECONDS);
        scheduler.scheduleAtFixedRate(new GuildRulesTask(), 0, 5, TimeUnit.MINUTES);
        scheduler.scheduleAtFixedRate(new ChannelGuidelinesTask(), 0, 5, TimeUnit.MINUTES);
    }


    private void shutdown() {
        logger.info("Program shutdown initiated");

        logger.info("Stopping tasks");
        scheduler.shutdown();

        logger.info("Shutting down bot");
        if (discordBot != null) {
            discordBot.shutdown();
        }

        logger.info("Shutting down database");
        Database.getInstance().shutdown();

        logger.info("Program shutdown complete");
    }

}
