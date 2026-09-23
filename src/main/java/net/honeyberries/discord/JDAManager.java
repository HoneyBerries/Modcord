package net.honeyberries.discord;

import net.dv8tion.jda.api.JDA;
import net.dv8tion.jda.api.JDABuilder;
import net.dv8tion.jda.api.entities.Activity;
import net.dv8tion.jda.api.hooks.ListenerAdapter;
import net.dv8tion.jda.api.requests.GatewayIntent;
import net.dv8tion.jda.api.requests.restaction.CommandListUpdateAction;
import net.honeyberries.discord.listener.GuildListener;
import net.honeyberries.discord.listener.MessageListener;
import net.honeyberries.discord.listener.RoleListener;
import net.honeyberries.discord.listener.UserListener;
import net.honeyberries.discord.slashCommands.ActionCommands;
import net.honeyberries.discord.slashCommands.AppealCommands;
import net.honeyberries.discord.slashCommands.DebugCommands;
import net.honeyberries.discord.slashCommands.ExcludeCommand;
import net.honeyberries.discord.slashCommands.HelpCommands;
import net.honeyberries.discord.slashCommands.ModerationCommands;
import net.honeyberries.discord.slashCommands.PreferencesCommands;
import net.honeyberries.discord.slashCommands.RollbackCommands;
import net.honeyberries.discord.slashCommands.ShutdownCommands;
import net.honeyberries.discord.slashCommands.StatusCommands;
import net.honeyberries.util.TokenManager;
import org.jetbrains.annotations.NotNull;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.function.BiConsumer;


/**
 * Singleton manager for the JDA (Java Discord API) instance.
 * Handles bot initialization, event listeners, and slash command registration.
 */
public class JDAManager {

    private static JDAManager instance;
    private static final Logger logger = LoggerFactory.getLogger(JDAManager.class);

    private final @NotNull JDA jda;

    /**
     * Initializes the JDA instance with all gateway intents enabled except {@link GatewayIntent#GUILD_PRESENCES},
     * which the bot does not use.
     * Retrieves bot token via {@link TokenManager}, sets activity status,
     * and awaits bot readiness.
     *
     * @throws RuntimeException if JDA initialization is interrupted
     */
    private JDAManager() {
        logger.info("Creating Discord bot instance");

        try {
            this.jda = JDABuilder.createDefault(
                    TokenManager.getDiscordBotToken(),
                    GatewayIntent.getIntents(GatewayIntent.ALL_INTENTS)
            ).disableIntents(GatewayIntent.GUILD_PRESENCES)
                    .setActivity(Activity.watching("your server while you sleep")).build();

            this.jda.awaitReady();
            logger.info("Discord bot connected as {}", jda.getSelfUser().getName());
        } catch (InterruptedException e) {
            logger.error("Failed to initializeFromConfig Discord bot", e);
            Thread.currentThread().interrupt();
            throw new RuntimeException("Failed to initializeFromConfig Discord bot", e);
        }
    }

    /**
     * Registers slash commands and attaches event listeners.
     * Sets up {@link GuildListener}, {@link MessageListener}, {@link UserListener},
     * {@link RoleListener}, and command handlers for status, debug, exclude, moderation, and preferences.
     * All commands are queued for synchronization with Discord.
     */
    private void registerCommands() {
        logger.info("Registering slash commands");
        CommandListUpdateAction commands = jda.updateCommands();

        jda.addEventListener(new GuildListener());
        jda.addEventListener(new MessageListener());
        jda.addEventListener(new UserListener());
        jda.addEventListener(new RoleListener());

        registerCommandHandler(new ShutdownCommands(), ShutdownCommands::registerShutdownCommands, "ShutdownCommands", commands);
        registerCommandHandler(new StatusCommands(), StatusCommands::registerStatusCommands, "StatusCommands", commands);
        registerCommandHandler(new DebugCommands(), DebugCommands::registerDebugCommands, "DebugCommands", commands);
        registerCommandHandler(new ExcludeCommand(), ExcludeCommand::registerExcludeCommands, "ExcludeCommand", commands);
        registerCommandHandler(new PreferencesCommands(), PreferencesCommands::registerPreferencesCommands, "PreferencesCommands", commands);
        registerCommandHandler(new ModerationCommands(), ModerationCommands::registerModerationCommands, "ModerationCommands", commands);
        registerCommandHandler(new ActionCommands(), ActionCommands::registerActionCommands, "ActionCommands", commands);
        registerCommandHandler(new RollbackCommands(), RollbackCommands::registerRollbackCommands, "RollbackCommands", commands);
        registerCommandHandler(new AppealCommands(), AppealCommands::registerAppealCommands, "AppealCommands", commands);
        registerCommandHandler(new HelpCommands(), HelpCommands::registerHelpCommands, "HelpCommands", commands);

        commands.queue();
        logger.info("All slash commands synced — bot setup complete");
    }

    /**
     * Registers a single slash-command handler: attaches it as an event listener, lets it
     * queue its own commands onto the shared {@link CommandListUpdateAction}, and logs completion.
     * Collapses the repeated "add listener, register commands, log" shape used for every
     * command handler in {@link #registerCommands()} into a single call site per handler.
     *
     * @param handler  the command handler instance to register; also attached as an event listener
     * @param register callback that has {@code handler} queue its slash commands onto {@code commands}
     * @param name     human-readable name of the handler, used only for the completion log message
     * @param commands the shared command update action to queue commands onto
     * @param <T>      the handler type, must extend {@link ListenerAdapter}
     */
    private <T extends ListenerAdapter> void registerCommandHandler(
            @NotNull T handler,
            @NotNull BiConsumer<T, CommandListUpdateAction> register,
            @NotNull String name,
            @NotNull CommandListUpdateAction commands) {
        jda.addEventListener(handler);
        register.accept(handler, commands);
        logger.info("Added {} to queue", name);
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