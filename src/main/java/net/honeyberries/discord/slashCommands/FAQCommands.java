package net.honeyberries.discord.slashCommands;

import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.events.interaction.command.SlashCommandInteractionEvent;
import net.dv8tion.jda.api.hooks.ListenerAdapter;
import net.dv8tion.jda.api.interactions.InteractionContextType;
import net.dv8tion.jda.api.interactions.commands.build.Commands;
import net.dv8tion.jda.api.requests.restaction.CommandListUpdateAction;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.preferences.PreferencesManager;
import net.honeyberries.ui.WelcomeEmbedUI;
import net.honeyberries.util.SlashCommandUtils;
import org.jetbrains.annotations.NotNull;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.Objects;

/**
 * Slash command handler for {@code /faq}, which shows the same overview Modcord posts when it joins a server.
 * Open to everyone: no permission is required.
 */
public class FAQCommands extends ListenerAdapter {

    private static final Logger logger = LoggerFactory.getLogger(FAQCommands.class);

    /**
     * Registers the {@code /faq} slash command.
     *
     * @param commands the command list to register onto; must not be null
     */
    public void registerFaqCommands(@NotNull CommandListUpdateAction commands) {
        Objects.requireNonNull(commands, "commands must not be null");
        commands.addCommands(Commands.slash("faq", "What Modcord does and how to get started").setContexts(InteractionContextType.GUILD));
        logger.info("Registered /faq command");
    }

    @Override
    public void onSlashCommandInteraction(@NotNull SlashCommandInteractionEvent event) {
        Objects.requireNonNull(event, "event must not be null");
        if (!event.getName().equals("faq")) {
            return;
        }

        Guild guild = event.getGuild();
        if (guild == null) {
            SlashCommandUtils.replyEphemeral(event, "This command only works in a server.");
            return;
        }

        SlashCommandUtils.replyEphemeral(event, WelcomeEmbedUI.build(
                PreferencesManager.getInstance().getOrDefaultPreferences(GuildID.fromGuild(guild))));
    }
}
