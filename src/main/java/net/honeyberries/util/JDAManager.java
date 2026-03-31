package net.honeyberries.util;

import net.dv8tion.jda.api.JDA;
import net.dv8tion.jda.api.JDABuilder;
import net.dv8tion.jda.api.entities.Activity;
import net.dv8tion.jda.api.requests.GatewayIntent;
import net.dv8tion.jda.api.requests.restaction.CommandListUpdateAction;
import net.honeyberries.discord.listener.MessageListener;
import net.honeyberries.discord.slashCommands.DebugCommands;
import net.honeyberries.discord.slashCommands.StatusCommands;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Singleton manager for accessing the JDA bot instance globally.
 * Handles lazy initialization, listener registration, and slash command synchronization so callers only request the ready client.
 */
public class JDAManager {

    private static final @NotNull JDAManager INSTANCE = new JDAManager();
    private final Logger logger = LoggerFactory.getLogger(JDAManager.class);

    private @Nullable JDA jda;

    private JDAManager() {
    }

    /**
     * Returns the shared manager instance.
     *
     * @return singleton {@link JDAManager}
     */
    @NotNull
    public static JDAManager getInstance() {
        return INSTANCE;
    }

    /**
     * Initializes the Discord bot, registers listeners, and syncs slash commands.
     * If the bot has already been created, the existing instance is returned.
     *
     * @return ready JDA instance
     * @throws InterruptedException if startup is interrupted
     */
    @NotNull
    public synchronized JDA initializeBot() throws InterruptedException {
        if (jda != null) {
            return jda;
        }

        logger.info("Creating Discord bot instance");
        Activity activity = Activity.watching("your server while you sleep");
        JDA initializedJda = JDABuilder.createDefault(
                TokenManager.getDiscordBotToken(),
                GatewayIntent.getIntents(GatewayIntent.ALL_INTENTS)
        ).setActivity(activity).build();

        initializedJda.awaitReady();
        jda = initializedJda;

        logger.info("Discord bot is connected as {}", initializedJda.getSelfUser().getName());

        CommandListUpdateAction commands = initializedJda.updateCommands();

        initializedJda.addEventListener(new MessageListener());

        StatusCommands statusCommands = new StatusCommands();
        initializedJda.addEventListener(statusCommands);
        statusCommands.registerStatusCommands(commands);
        logger.info("Added StatusCommands to queue");

        DebugCommands debugCommands = new DebugCommands();
        initializedJda.addEventListener(debugCommands);
        debugCommands.registerDebugCommands(commands);
        logger.info("Added DebugCommands to queue");

        commands.queue();
        logger.info("All slash commands synced with Discord successfully");
        logger.info("Discord bot setup complete");

        return initializedJda;
    }



    /**
     * Gets the initialized JDA instance if available.
     *
     * @return the JDA instance, or {@code null} if {@link #initializeBot()} has not been called yet
     */
    @Nullable
    public JDA getJDA() {
        return jda;
    }
}
