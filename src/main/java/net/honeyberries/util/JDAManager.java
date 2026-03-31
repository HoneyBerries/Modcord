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


public class JDAManager {

    private static final @NotNull JDAManager INSTANCE = new JDAManager();
    private final Logger logger = LoggerFactory.getLogger(JDAManager.class);

    private @Nullable JDA jda;

    private JDAManager() {}

    @NotNull
    public static JDAManager getInstance() {
        return INSTANCE;
    }



    /**
     * Returns the ready JDA instance, initializing it on first call.
     *
     * @return ready {@link JDA} instance
     * @throws InterruptedException if startup is interrupted
     */
    @NotNull
    public synchronized JDA getJDA() throws InterruptedException {
        if (jda != null) return jda;

        logger.info("Creating Discord bot instance");

        jda = JDABuilder.createDefault(
                TokenManager.getDiscordBotToken(),
                GatewayIntent.getIntents(GatewayIntent.ALL_INTENTS)
        ).setActivity(Activity.watching("your server while you sleep")).build();

        jda.awaitReady();
        logger.info("Discord bot connected as {}", jda.getSelfUser().getName());

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

        commands.queue();
        logger.info("All slash commands synced — bot setup complete");

        return jda;
    }
}