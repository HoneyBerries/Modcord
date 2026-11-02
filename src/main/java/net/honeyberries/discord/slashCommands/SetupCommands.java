package net.honeyberries.discord.slashCommands;

import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.events.interaction.command.SlashCommandInteractionEvent;
import net.dv8tion.jda.api.events.interaction.component.ButtonInteractionEvent;
import net.dv8tion.jda.api.events.interaction.component.StringSelectInteractionEvent;
import net.dv8tion.jda.api.hooks.ListenerAdapter;
import net.dv8tion.jda.api.interactions.callbacks.IMessageEditCallback;
import net.dv8tion.jda.api.interactions.commands.build.Commands;
import net.dv8tion.jda.api.requests.restaction.CommandListUpdateAction;
import net.dv8tion.jda.api.utils.messages.MessageEditData;
import net.honeyberries.ui.SetupEmbedUI;
import net.honeyberries.util.PreferenceCommandHelper;
import net.honeyberries.util.SlashCommandUtils;
import org.jetbrains.annotations.NotNull;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.Objects;

/**
 * Slash command {@code /setup}: a first-run checklist for the current guild covering
 * preferences, bot permissions and role hierarchy. Admin-only, same gate as {@code /preferences}.
 */
public class SetupCommands extends ListenerAdapter {

    private static final Logger logger = LoggerFactory.getLogger(SetupCommands.class);

    private final PreferenceCommandHelper helper = new PreferenceCommandHelper();

    /**
     * Registers the {@code /setup} slash command.
     *
     * @param commands the command list to register onto; must not be null
     */
    public void registerSetupCommands(@NotNull CommandListUpdateAction commands) {
        Objects.requireNonNull(commands, "commands must not be null");
        commands.addCommands(Commands.slash("setup", "Check this server's Modcord setup (permissions, channels, role order)"));
        logger.info("Registered /setup command");
    }

    @Override
    public void onStringSelectInteraction(@NotNull StringSelectInteractionEvent event) {
        if (event.getComponentId().startsWith(SetupEmbedUI.ID_PREFIX)) {
            showPage(event, event.getValues().getFirst());
        }
    }

    @Override
    public void onButtonInteraction(@NotNull ButtonInteractionEvent event) {
        String id = event.getComponentId();
        if (id.startsWith(SetupEmbedUI.RECHECK_PREFIX)) {
            showPage(event, id.substring(SetupEmbedUI.RECHECK_PREFIX.length()));
        }
    }

    /** Re-renders the {@code /setup} message in place for the given page. */
    private void showPage(@NotNull IMessageEditCallback event, @NotNull String page) {
        Guild guild = event.getGuild();
        if (guild != null) {
            event.editMessage(MessageEditData.fromCreateData(SetupEmbedUI.buildMessage(guild, page))).queue();
        }
    }

    @Override
    public void onSlashCommandInteraction(@NotNull SlashCommandInteractionEvent event) {
        Objects.requireNonNull(event, "event must not be null");
        if (!event.getName().equals("setup")) {
            return;
        }
        Guild guild = helper.validateGuildAndPermissions(event);
        if (guild == null) {return;}

        try {
            SlashCommandUtils.replyEphemeral(event, SetupEmbedUI.buildMessage(guild, SetupEmbedUI.STATUS));
        } catch (Exception e) {
            logger.error("Error handling /setup in guild {}", guild.getId(), e);
            SlashCommandUtils.replyEphemeral(event, "An unexpected error occurred while processing the command.");
        }
    }
}
