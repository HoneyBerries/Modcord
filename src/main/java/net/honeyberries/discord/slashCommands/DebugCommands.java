package net.honeyberries.discord.slashCommands;

import net.dv8tion.jda.api.Permission;
import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.channel.concrete.TextChannel;
import net.dv8tion.jda.api.hooks.ListenerAdapter;
import net.dv8tion.jda.api.interactions.commands.DefaultMemberPermissions;
import net.dv8tion.jda.api.events.interaction.command.SlashCommandInteractionEvent;
import net.dv8tion.jda.api.interactions.commands.build.*;
import net.dv8tion.jda.api.interactions.commands.OptionType;
import net.dv8tion.jda.api.requests.restaction.CommandListUpdateAction;
import net.honeyberries.database.GuildRulesRepository;
import net.honeyberries.datatypes.content.GuildRules;
import net.honeyberries.datatypes.discord.GuildID;
import org.jetbrains.annotations.NotNull;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.Objects;

public class DebugCommands extends ListenerAdapter {

    private static final Logger logger = LoggerFactory.getLogger(DebugCommands.class);
    private final GuildRulesRepository rulesRepo = GuildRulesRepository.getInstance();

    public void registerDebugCommands(CommandListUpdateAction commands) {
        SubcommandData refreshSub = new SubcommandData(
                "refresh-rules-and-guidelines",
                "Refreshes the rules and guidelines in the configured channel"
        );

        SubcommandData showSub = new SubcommandData(
                "show-rules-and-guidelines",
                "Shows the current rules and guidelines"
        );

        SubcommandData purgeSub = new SubcommandData("purge", "Deletes and recreates a channel")
                .addOptions(new OptionData(OptionType.CHANNEL, "channel", "Channel to delete and recreate", true));

        SlashCommandData debugCommand = Commands.slash("debug", "Debug and admin commands")
                .addSubcommands(refreshSub, showSub, purgeSub)
                .setDefaultPermissions(DefaultMemberPermissions.enabledFor(Permission.ADMINISTRATOR));

        commands.addCommands(debugCommand);
        logger.info("Debug commands added to command registration");
    }

    @Override
    public void onSlashCommandInteraction(@NotNull SlashCommandInteractionEvent event) {
        if (!event.getName().equals("debug")) {
            return;
        }

        if (!event.isFromGuild()) {
            event.reply("This command can only be used in servers!").setEphemeral(true).queue();
            return;
        }

        if (event.getMember() != null && !event.getMember().hasPermission(Permission.ADMINISTRATOR)) {
            event.reply("You need administrator permissions to use this command").setEphemeral(true).queue();
            return;
        }

        String commandName = event.getSubcommandName();
        switch (Objects.requireNonNull(commandName)) {
            case "refresh-rules-and-guidelinesText" -> handleRefreshRulesAndGuidelines(event);
            case "show-rules-and-guidelinesText" -> handleShowRulesAndGuidelines(event);
            case "purge" -> handlePurge(event);
            default -> event.reply("Unknown command").setEphemeral(true).queue();
        }
    }

    private void handleRefreshRulesAndGuidelines(@NotNull SlashCommandInteractionEvent event) {
        try {
            GuildID guildId = new GuildID(Objects.requireNonNull(event.getGuild()).getIdLong());
            GuildRules rules = rulesRepo.getGuildRules(guildId);

            if (rules == null) {
                event.reply("No rules found for this guild. Please set rules first.").setEphemeral(true).queue();
                return;
            }

            event.reply("Rules and guidelinesText refreshed successfully!").setEphemeral(true).queue();
            logger.debug("Refreshed rules for guild: {}", guildId.value());
        } catch (Exception e) {
            logger.error("Error refreshing rules and guidelinesText", e);
            event.reply("Failed to refresh rules and guidelinesText").setEphemeral(true).queue();
        }
    }

    private void handleShowRulesAndGuidelines(@NotNull SlashCommandInteractionEvent event) {
        try {
            GuildID guildId = new GuildID(Objects.requireNonNull(event.getGuild()).getIdLong());
            GuildRules rules = rulesRepo.getGuildRules(guildId);

            if (rules == null) {
                event.reply("No rules found for this guild.").setEphemeral(true).queue();
                return;
            }

            String message = "**Current Guild Rules:**\n\n" + rules.rulesText();
            event.reply(message).setEphemeral(true).queue();
            logger.debug("Showed rules for guild: {}", guildId.value());
        } catch (Exception e) {
            logger.error("Error showing rules and guidelinesText", e);
            event.reply("Failed to retrieve rules and guidelinesText").setEphemeral(true).queue();
        }
    }

    private void handlePurge(@NotNull SlashCommandInteractionEvent event) {
        try {
            TextChannel targetChannel = event.getOption("channel", null, option ->
                    option.getAsChannel().asTextChannel()
            );

            if (targetChannel == null) {
                event.reply("Please specify a valid text channel").setEphemeral(true).queue();
                return;
            }

            String channelName = targetChannel.getName();
            int position = targetChannel.getPositionRaw();
            String topic = targetChannel.getTopic();
            Guild guild = event.getGuild();

            // Reply first so the interaction doesn't break when the channel vanishes
            event.reply("Purging " + targetChannel.getAsMention() + "...").setEphemeral(true).queue();

            targetChannel.delete().queue(
                deleted -> {
                    assert guild != null;
                    guild.createTextChannel(channelName)
                            .setPosition(position)
                            .setTopic(topic)
                            .queue(
                                newChannel -> logger.debug("Purged channel: {} in guild: {}", channelName, guild.getId()),
                                throwable -> logger.error("Failed to recreate channel", throwable)
                            );
                },
                throwable -> logger.error("Failed to delete channel", throwable)
            );
        } catch (Exception e) {
            logger.error("Error purging channel", e);
            event.reply("Failed to purge channel").setEphemeral(true).queue();
        }
    }
}
