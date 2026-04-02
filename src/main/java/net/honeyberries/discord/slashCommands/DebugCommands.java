package net.honeyberries.discord.slashCommands;

import net.dv8tion.jda.api.Permission;
import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.Message;
import net.dv8tion.jda.api.entities.channel.Channel;
import net.dv8tion.jda.api.entities.channel.concrete.TextChannel;
import net.dv8tion.jda.api.hooks.ListenerAdapter;
import net.dv8tion.jda.api.interactions.commands.DefaultMemberPermissions;
import net.dv8tion.jda.api.events.interaction.command.SlashCommandInteractionEvent;
import net.dv8tion.jda.api.interactions.commands.build.*;
import net.dv8tion.jda.api.interactions.commands.OptionType;
import net.dv8tion.jda.api.requests.restaction.CommandListUpdateAction;
import net.honeyberries.database.GuildPreferencesRepository;
import net.honeyberries.database.GuildRulesRepository;
import net.honeyberries.datatypes.content.GuildRules;
import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.preferences.GuildPreferences;
import net.honeyberries.message.EmbedParser;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.List;
import java.util.Objects;
import java.util.concurrent.ExecutionException;
import java.util.stream.Collectors;

public class DebugCommands extends ListenerAdapter {

    private static final Logger logger = LoggerFactory.getLogger(DebugCommands.class);
    private final GuildRulesRepository rulesRepo = GuildRulesRepository.getInstance();
    private final GuildPreferencesRepository preferencesRepo = GuildPreferencesRepository.getInstance();

    public void registerDebugCommands(CommandListUpdateAction commands) {
        SubcommandData refreshSub = new SubcommandData(
                "refresh-rules",
                "Refreshes the rules from the configured channel"
        );

        SubcommandData showSub = new SubcommandData(
                "show-rules",
                "Shows the current rules"
        );

        SubcommandData purgeSub = new SubcommandData("purge", "Deletes and recreates a channel")
                .addOptions(new OptionData(OptionType.CHANNEL, "channel", "Channel to delete and recreate", true));

        SlashCommandData debugCommand = Commands.slash("debug", "Debug and admin commands")
                .addSubcommands(refreshSub, showSub, purgeSub)
                .setDefaultPermissions(DefaultMemberPermissions.enabledFor(Permission.MANAGE_SERVER));

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
            case "refresh-rules" -> handleRefreshRules(event);
            case "show-rules" -> handleShowRules(event);
            case "purge" -> handlePurge(event);
            default -> event.reply("Unknown command").setEphemeral(true).queue();
        }
    }

    private void handleRefreshRules(@NotNull SlashCommandInteractionEvent event) {
        try {
            Guild guild = Objects.requireNonNull(event.getGuild());
            GuildID guildId = new GuildID(guild.getIdLong());
            GuildRules rules = refreshRulesFromDiscord(guild, guildId);

            GuildRulesRepository.getInstance().addOrReplaceGuildRulesToDatabase(rules);

            if (rules == null || rules.rulesText() == null || rules.rulesText().isBlank()) {
                event.reply("No rules found in the configured rules channel. Check channel ID, permissions, and channel content.")
                        .setEphemeral(true)
                        .queue();
                return;
            }

            event.reply("Rules refreshed successfully!").setEphemeral(true).queue();
            logger.debug("Refreshed rules for guild: {}", guildId.value());
        } catch (Exception e) {
            logger.error("Error refreshing rules", e);
            event.reply("Failed to refresh rules").setEphemeral(true).queue();
        }
    }

    private void handleShowRules(@NotNull SlashCommandInteractionEvent event) {
        try {
            Guild guild = Objects.requireNonNull(event.getGuild());
            GuildID guildId = new GuildID(guild.getIdLong());
            GuildRules rules = rulesRepo.getGuildRulesFromCache(guildId);

            if (rules == null || rules.rulesText() == null || rules.rulesText().isBlank()) {
                rules = refreshRulesFromDiscord(guild, guildId);
                if (rules == null || rules.rulesText() == null || rules.rulesText().isBlank()) {
                    event.reply("No rules are currently configured for this guild.").setEphemeral(true).queue();
                    return;
                }
            }

            String message = "**Current Guild Rules:**\n\n" + rules.rulesText();
            event.reply(message).setEphemeral(true).queue();
            logger.debug("Showed rules for guild: {}", guildId.value());
        } catch (Exception e) {
            logger.error("Error showing rules", e);
            event.reply("Failed to retrieve rules").setEphemeral(true).queue();
        }
    }

    @Nullable
    private GuildRules refreshRulesFromDiscord(@NotNull Guild guild, @NotNull GuildID guildId) {
        GuildRules existingRules = rulesRepo.getGuildRulesFromCache(guildId);
        ChannelID rulesChannelId = existingRules != null ? existingRules.rulesChannelId() : null;

        if (rulesChannelId == null) {
            GuildPreferences preferences = preferencesRepo.getGuildPreferences(guildId);
            rulesChannelId = preferences != null ? preferences.rulesChannelID() : null;
        }

        if (rulesChannelId == null) {
            return existingRules;
        }

        String refreshedRulesText = fetchRulesTextFromChannel(guild, rulesChannelId);
        if (refreshedRulesText == null || refreshedRulesText.isBlank()) {
            return new GuildRules(guildId, rulesChannelId, null);
        }

        GuildRules refreshed = new GuildRules(guildId, rulesChannelId, refreshedRulesText);
        boolean saved = rulesRepo.addOrReplaceGuildRulesToDatabase(refreshed);
        if (!saved) {
            logger.warn("Failed to persist refreshed rules for guild {}", guildId.value());
        }
        return refreshed;
    }

    @Nullable
    private String fetchRulesTextFromChannel(@NotNull Guild guild, @NotNull ChannelID rulesChannelId) {
        Channel rulesChannel = guild.getGuildChannelById(rulesChannelId.value());
        if (!(rulesChannel instanceof TextChannel rulesTextChannel)) {
            return null;
        }

        try {
            List<Message> messages = rulesTextChannel.getHistory()
                    .retrievePast(100)
                    .submit()
                    .get();

            return messages.reversed().stream()
                    .map(this::extractRuleText)
                    .filter(s -> !s.isBlank())
                    .collect(Collectors.joining("\n\n"));
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            logger.warn("Interrupted while fetching rules for guild {}", guild.getId());
            return null;
        } catch (ExecutionException e) {
            logger.warn("Failed to fetch rules for guild {}", guild.getId(), e);
            return null;
        }
    }

    private String extractRuleText(@NotNull Message message) {
        String content = message.getContentDisplay();
        String embed = EmbedParser.parseEmbed(message);

        boolean hasContent = content != null && !content.isBlank();
        boolean hasEmbed = !embed.isBlank();

        if (hasContent && hasEmbed) {
            return content + "\n" + embed;
        }
        if (hasContent) {
            return content;
        }
        return hasEmbed ? embed : "";
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