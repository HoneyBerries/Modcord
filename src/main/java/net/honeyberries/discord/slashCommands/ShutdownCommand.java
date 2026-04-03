package net.honeyberries.discord.slashCommands;

import net.dv8tion.jda.api.Permission;
import net.dv8tion.jda.api.events.interaction.command.SlashCommandInteractionEvent;
import net.dv8tion.jda.api.hooks.ListenerAdapter;
import net.dv8tion.jda.api.interactions.commands.DefaultMemberPermissions;
import net.dv8tion.jda.api.interactions.commands.build.Commands;
import net.dv8tion.jda.api.interactions.commands.build.SlashCommandData;
import net.dv8tion.jda.api.requests.restaction.CommandListUpdateAction;
import net.honeyberries.Main;
import org.jetbrains.annotations.NotNull;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.Objects;

/**
 * Slash command handler for graceful bot shutdown.
 *
 * <p>Provides administrators with a safe way to shut down the bot through Discord. 
 * The shutdown command requires administrator permissions and is only available in 
 * guild contexts. This helps ensure the bot can be stopped cleanly through its 
 * command interface rather than requiring process management access.
 */
public class ShutdownCommand extends ListenerAdapter {

    private static final Logger logger = LoggerFactory.getLogger(ShutdownCommand.class);

    /**
     * Registers the shutdown command with the Discord bot.
     *
     * @param commands the command list update action to register commands with. Must not be null.
     * @throws NullPointerException if commands is null
     */
    public void registerShutdownCommand(@NotNull CommandListUpdateAction commands) {
        Objects.requireNonNull(commands, "commands must not be null");
        SlashCommandData shutdownCommand = Commands.slash("shutdown", "Gracefully shutdown the bot")
                .setDefaultPermissions(DefaultMemberPermissions.enabledFor(Permission.ADMINISTRATOR));

        commands.addCommands(shutdownCommand);
        logger.info("Registered /shutdown command");
    }

    /**
     * Handles slash command interactions for the shutdown command.
     *
     * <p>Only responds to the "shutdown" command. Validates that the invoker has 
     * administrator permissions and the command is executed in a guild. Sends an 
     * acknowledgment to Discord before initiating the shutdown sequence. Logs the 
     * shutdown event with the user who initiated it.
     *
     * @param event the slash command interaction event. Must not be null.
     * @throws NullPointerException if event is null
     */
    @Override
    public void onSlashCommandInteraction(@NotNull SlashCommandInteractionEvent event) {
        Objects.requireNonNull(event, "event must not be null");
        if (!event.getName().equals("shutdown")) {
            return;
        }

        if (!event.isFromGuild()) {
            event.reply("This command can only be used in servers!").setEphemeral(true).queue();
            return;
        }

        if (event.getMember() == null || !event.getMember().hasPermission(Permission.ADMINISTRATOR)) {
            event.reply("You need administrator permissions to use this command").setEphemeral(true).queue();
            return;
        }

        event.reply("Shutting down bot...").setEphemeral(true).queue();
        logger.info("Shutdown initiated by user {} in guild {}", event.getUser().getId(), Objects.requireNonNull(event.getGuild()).getId());

        Main.shutdown();
    }
}
