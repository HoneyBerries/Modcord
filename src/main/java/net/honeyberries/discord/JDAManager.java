package net.honeyberries.discord;

import net.dv8tion.jda.api.JDA;
import net.dv8tion.jda.api.JDABuilder;
import net.dv8tion.jda.api.entities.Activity;
import net.dv8tion.jda.api.requests.GatewayIntent;
import net.dv8tion.jda.api.requests.restaction.CommandListUpdateAction;
import net.honeyberries.discord.listener.MessageListener;
import net.honeyberries.discord.slashCommands.DebugCommands;
import net.honeyberries.discord.slashCommands.ExcludeCommand;
import net.honeyberries.discord.slashCommands.StatusCommands;
import net.honeyberries.util.TokenManager;
import org.jetbrains.annotations.NotNull;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;


public class JDAManager {

    private static JDAManager instance;
    private static final Logger logger = LoggerFactory.getLogger(JDAManager.class);

    private final @NotNull JDA jda;

    private JDAManager() {
        logger.info("Creating Discord bot instance");

        try {
            this.jda = JDABuilder.createDefault(
                    TokenManager.getDiscordBotToken(),
                    GatewayIntent.getIntents(GatewayIntent.ALL_INTENTS)
            ).setActivity(Activity.watching("your server while you sleep")).build();

            this.jda.awaitReady();
            logger.info("Discord bot connected as {}", jda.getSelfUser().getName());
        } catch (InterruptedException e) {
            logger.error("Failed to initialize Discord bot", e);
            Thread.currentThread().interrupt();
            throw new RuntimeException("Failed to initialize Discord bot", e);
        }
    }

    private void registerCommands() {
        logger.info("Registering slash commands");
        CommandListUpdateAction commands = jda.updateCommands();

        jda.addEventListener(new MessageListener());

        StatusCommands statusCommands = new StatusCommands();
        jda.addEventListener(statusCommands);
        statusCommands.registerStatusCommands(commands);
        logger.info("Added StatusCommands to queue");

        DebugCommands debugCommands = new DebugCommands();
        jda.addEventListener(debugCommands);
        debugCommands.registerDebugCommands(commands);
        logger.info("Added DebugCommands to queue");

        ExcludeCommand excludeCommand = new ExcludeCommand();
        jda.addEventListener(excludeCommand);
        excludeCommand.registerExcludeCommands(commands);
        logger.info("Added ExcludeCommand to queue");

        commands.queue();
        logger.info("All slash commands synced — bot setup complete");
    }

    @NotNull
    public static synchronized JDAManager getInstance() {
        if (instance == null) {
            logger.info("Creating JDAManager instance");
            instance = new JDAManager();
            logger.info("JDAManager instance created");

            instance.registerCommands();
        }
        return instance;
    }

    /**
     * Returns the ready JDA instance.
     *
     * @return ready {@link JDA} instance
     */
    @NotNull
    public JDA getJDA() {
        return jda;
    }
}