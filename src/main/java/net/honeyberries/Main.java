package net.honeyberries;


import net.dv8tion.jda.api.JDA;
import net.honeyberries.config.AppConfig;
import net.honeyberries.database.Database;
import net.honeyberries.task.ChannelGuidelinesTask;
import net.honeyberries.task.GuildRulesTask;
import net.honeyberries.task.UnbanWatcherTask;
import net.honeyberries.util.JDAManager;
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
        discordBot = JDAManager.getInstance().initializeBot();
    }


    private void setupTasks() {
        scheduler = Executors.newScheduledThreadPool(8);

        scheduler.scheduleAtFixedRate(new UnbanWatcherTask(), 0, 10, TimeUnit.SECONDS);
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
        System.exit(0);
    }

}
