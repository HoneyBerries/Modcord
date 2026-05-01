package net.honeyberries;

import net.dv8tion.jda.api.JDA;
import net.honeyberries.config.AppConfig;
import net.honeyberries.database.Database;
import net.honeyberries.discord.JDAManager;
import net.honeyberries.services.GlobalOrchestrationService;
import net.honeyberries.task.ChannelGuidelinesTask;
import net.honeyberries.task.GuildRulesTask;
import net.honeyberries.task.UnbanWatcherTask;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import sun.misc.Signal;

import java.nio.file.Paths;
import java.util.Objects;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Application entry point responsible for wiring together the database, Discord bot, and recurring maintenance tasks.
 * Initializes shared services, schedules periodic synchronization jobs, and orchestrates orderly shutdown when invoked in test mode.
 */
public class Main {

    /** Logger used for lifecycle events. */
    private static final Logger logger = LoggerFactory.getLogger(Main.class);
    /** JDA client instance, lazily initialized during startup. */
    private static @Nullable JDA discordBot;
    /** Scheduler hosting recurring maintenance tasks. */
    private static @Nullable ScheduledExecutorService scheduler;
    /** Guards against re-entrant or concurrent shutdown calls. */
    private static final AtomicBoolean shuttingDown = new AtomicBoolean(false);

    static {
        ResourceInitializer.initialize();
    }

    /**
     * Boots the application by preparing the database, connecting to Discord, and starting background tasks.
     * When invoked with {@code --test}, the process will shut down automatically after a short grace period to let tests complete.
     *
     * @param args command-line arguments; {@code --test} triggers automatic shutdown
     */
    static void main(@NotNull String[] args) {
        Objects.requireNonNull(args, "args must not be null");

        Signal.handle(new Signal("TERM"), sig -> {
            logger.info("Received SIGTERM, initiating shutdown");
            shutdown();
        });
        Signal.handle(new Signal("INT"), sig -> {
            logger.info("Received SIGINT (Ctrl+C), initiating shutdown");
            shutdown();
        });

        Main main = new Main();
        try {
            main.setupDatabase();
            main.setupDiscordBot();
            main.setupTasks();
        } finally {
            if (args.length != 0 && args[0].equalsIgnoreCase("--test")) {
                Thread.startVirtualThread(() -> {
                    try {
                        Thread.sleep(5000); // Wait for 5 seconds before shutting down
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                    } finally {
                        shutdown();
                    }
                });
            }

        }
    }

    /**
     * Loads configuration and initializes the database connection pool.
     * Uses {@code ./config/app_config.yml} relative to the working directory.
     */
    private void setupDatabase() {
        logger.info("Initializing database");
        AppConfig config = new AppConfig(Paths.get("./config/app_config.yml"));
        Database.getInstance().initialize(config);
        logger.info("Database initialized successfully");
    }

    /**
     * Connects to Discord via {@link JDAManager} and blocks until the JDA instance is ready.
     *
     */
    private void setupDiscordBot() {
        discordBot = JDAManager.getInstance().getJDA();
    }

    /**
     * Schedules recurring tasks for unban checks, rules synchronization, and channel guidelines updates.
     * Uses a fixed thread pool sized for concurrent polling of external resources.
     */
    private void setupTasks() {
        scheduler = Executors.newScheduledThreadPool(8);

        long rulesSyncInterval = Math.max(1L, Math.round(AppConfig.getInstance().getRulesSyncInterval()));
        long guidelinesSyncInterval = Math.max(1L, Math.round(AppConfig.getInstance().getGuidelinesSyncInterval()));

        scheduler.scheduleAtFixedRate(new UnbanWatcherTask(), 0, rulesSyncInterval, TimeUnit.SECONDS);
        scheduler.scheduleAtFixedRate(new GuildRulesTask(), 0, guidelinesSyncInterval, TimeUnit.SECONDS);
        scheduler.scheduleAtFixedRate(new ChannelGuidelinesTask(), 0, 5, TimeUnit.MINUTES);
    }

    /**
     * Safely stops background tasks, shuts down the bot, and closes the database before exiting.
     * Safe to invoke even if startup failed partway through.
     */
    public static void shutdown() {
        if (!shuttingDown.compareAndSet(false, true)) {
            return;
        }

        logger.info("Program shutdown initiated");

        logger.info("Stopping tasks");
        if (scheduler != null) {
            scheduler.shutdown();
            try {
                if (!scheduler.awaitTermination(15, TimeUnit.SECONDS)) {
                    logger.warn("Scheduled tasks did not stop in time, forcing shutdown");
                    scheduler.shutdownNow();
                    if (!scheduler.awaitTermination(5, TimeUnit.SECONDS)) {
                        logger.warn("Scheduled tasks are still running after forced shutdown");
                    }
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                logger.warn("Interrupted while waiting for scheduler shutdown, forcing cancellation");
                scheduler.shutdownNow();
            }
        }

        logger.info("Dropping pending moderation queues");
        GlobalOrchestrationService.getInstance().shutdownNowAndDropPending();

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
