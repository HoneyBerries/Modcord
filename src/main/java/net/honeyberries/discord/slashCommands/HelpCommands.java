package net.honeyberries.discord.slashCommands;

import net.dv8tion.jda.api.EmbedBuilder;
import net.dv8tion.jda.api.events.interaction.command.SlashCommandInteractionEvent;
import net.dv8tion.jda.api.hooks.ListenerAdapter;
import net.dv8tion.jda.api.interactions.commands.Command;
import net.dv8tion.jda.api.interactions.commands.build.Commands;
import net.dv8tion.jda.api.interactions.commands.build.SlashCommandData;
import net.dv8tion.jda.api.requests.restaction.CommandListUpdateAction;
import org.jetbrains.annotations.NotNull;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.awt.Color;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicReference;

/**
 * Slash command handler for bot help and command discovery.
 *
 * <p>Provides users with a dynamically-generated list of all available commands,
 * their descriptions, and subcommands. The command list is fetched from Discord's
 * command registry on first invocation and cached for subsequent calls.
 */
public class HelpCommands extends ListenerAdapter {

    private static final Logger logger = LoggerFactory.getLogger(HelpCommands.class);
    private final AtomicReference<List<Command>> commandCache = new AtomicReference<>();

    /**
     * Registers the help command with the Discord bot.
     *
     * @param commands the command list update action to register commands with. Must not be null.
     * @throws NullPointerException if commands is null
     */
    public void registerHelpCommands(@NotNull CommandListUpdateAction commands) {
        Objects.requireNonNull(commands, "commands must not be null");
        SlashCommandData helpCommand = Commands.slash(
                "help",
                "Lists all available bot commands and their descriptions"
        );

        commands.addCommands(helpCommand);
        logger.info("Registered /help command");
    }

    /**
     * Handles slash command interactions for the help command.
     *
     * <p>Fetches the list of all registered commands from Discord's API on first
     * invocation and caches the result. Formats the command list with descriptions
     * and subcommands and replies with an ephemeral message.
     *
     * @param event the slash command interaction event. Must not be null.
     * @throws NullPointerException if event is null
     */
    @Override
    public void onSlashCommandInteraction(@NotNull SlashCommandInteractionEvent event) {
        Objects.requireNonNull(event, "event must not be null");
        if (!event.getName().equals("help")) {
            return;
        }

        try {
            List<Command> registeredCommands = commandCache.get();
            if (registeredCommands == null) {
                registeredCommands = event.getJDA().retrieveCommands().complete();
                commandCache.compareAndSet(null, registeredCommands);
            }

            EmbedBuilder embed = new EmbedBuilder()
                    .setTitle("📖 Modcord Bot Commands")
                    .setColor(Color.BLUE);

            StringBuilder description = new StringBuilder();
            for (Command cmd : registeredCommands) {
                description.append(String.format("**`/%s`** — %s\n", cmd.getName(), cmd.getDescription()));
                for (Command.Subcommand sub : cmd.getSubcommands()) {
                    description.append(String.format("  ↳ `%s` — %s\n", sub.getName(), sub.getDescription()));
                }
                description.append("\n");
            }

            embed.setDescription(description.toString());
            event.replyEmbeds(embed.build()).setEphemeral(true).queue();
        } catch (Exception e) {
            logger.error("Error handling /help command", e);
            event.reply("An error occurred while fetching the command list.").setEphemeral(true).queue();
        }
    }
}
