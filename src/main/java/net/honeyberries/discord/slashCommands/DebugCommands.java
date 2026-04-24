package net.honeyberries.discord.slashCommands;

import net.dv8tion.jda.api.Permission;
import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.Message;
import net.dv8tion.jda.api.entities.channel.Channel;
import net.dv8tion.jda.api.entities.channel.concrete.TextChannel;
import net.dv8tion.jda.api.hooks.ListenerAdapter;
import net.dv8tion.jda.api.events.interaction.command.SlashCommandInteractionEvent;
import net.dv8tion.jda.api.interactions.commands.build.*;
import net.dv8tion.jda.api.interactions.commands.OptionType;
import net.dv8tion.jda.api.requests.restaction.CommandListUpdateAction;
import net.honeyberries.database.repository.GuildPreferencesRepository;
import net.honeyberries.database.repository.GuildRulesRepository;
import net.honeyberries.database.repository.SpecialUsersRepository;
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

/**
 * Slash command handler for debug and administrative commands.
 *
 * <p>Provides administrative utilities for server management including rule refreshing, 
 * viewing guild rules, and channel purging (delete and recreate). All commands require 
 * administrator permissions and are only usable in guild contexts. This suite helps 
 * administrators diagnose issues and manage server state.
 */
public class DebugCommands extends ListenerAdapter {

    private static final Logger logger = LoggerFactory.getLogger(DebugCommands.class);
    private final GuildRulesRepository rulesRepo = GuildRulesRepository.getInstance();
    private final GuildPreferencesRepository preferencesRepo = GuildPreferencesRepository.getInstance();

    /**
     * Registers the debug command and its subcommands with the Discord bot.
     *
     * @param commands the command list update action to register commands with. Must not be null.
     * @throws NullPointerException if commands is null
     */
    public void registerDebugCommands(@NotNull CommandListUpdateAction commands) {
        Objects.requireNonNull(commands, "commands must not be null");

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

        SlashCommandData debugCommand = Commands.slash("debug", "Debug and admin commands").addSubcommands(refreshSub, showSub, purgeSub);

        Objects.requireNonNull(commands.addCommands(debugCommand));
        logger.info("Debug commands added to command registration");
    }

    /**
     * Handles slash command interactions for the debug command.
     *
     * <p>Routes to appropriate subcommand handler (refresh-rules, show-rules, or purge) 
     * after validating permissions. Only responds to the "debug" command and requires 
     * guild context and administrator permissions.
     *
     * @param event the slash command interaction event. Must not be null.
     * @throws NullPointerException if event is null
     */
    @Override
    public void onSlashCommandInteraction(@NotNull SlashCommandInteractionEvent event) {
        Objects.requireNonNull(event, "event must not be null");
        if (!event.getName().equals("debug")) {
            return;
        }

        if (!event.isFromGuild()) {
            event.reply("This command can only be used in servers!").setEphemeral(true).queue();
            return;
        }

        boolean hasPermission = event.getMember() != null
                && (event.getMember().hasPermission(Permission.MANAGE_SERVER)
                || SpecialUsersRepository.getInstance().isSpecialUser(event.getUser()));

        if (!hasPermission) {
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

    /**
     * Handles the refresh-rules subcommand.
     *
     * <p>Fetches the latest rules from the configured rules channel in Discord and 
     * updates the guild's cached rules in the database. Notifies the user of success 
     * or failure via ephemeral reply.
     *
     * @param event the slash command interaction event. Must not be null.
     * @throws NullPointerException if event is null
     */
    private void handleRefreshRules(@NotNull SlashCommandInteractionEvent event) {
        Objects.requireNonNull(event, "event must not be null");
        try {
            Guild guild = Objects.requireNonNull(event.getGuild());
            GuildID guildId = new GuildID(guild.getIdLong());
            GuildRules rules = refreshRulesFromDiscord(guild, guildId);

            if (rules == null || rules.rulesText() == null || rules.rulesText().isBlank()) {
                event.reply("No rules found in the configured rules channel. Check channel ID, permissions, and channel content.")
                        .setEphemeral(true)
                        .queue();
                return;
            }

            GuildRulesRepository.getInstance().addOrReplaceGuildRulesToDatabase(rules);

            event.reply("Rules refreshed successfully!").setEphemeral(true).queue();
            logger.debug("Refreshed rules for guild: {}", guildId.value());
        } catch (Exception e) {
            logger.error("Error refreshing rules", e);
            event.reply("Failed to refresh rules").setEphemeral(true).queue();
        }
    }

    /**
     * Handles the show-rules subcommand.
     *
     * <p>Displays the currently cached guild rules to the user. If no cached rules exist, 
     * attempts to fetch and cache them from Discord first. Sends the rules as an 
     * ephemeral reply.
     *
     * @param event the slash command interaction event. Must not be null.
     * @throws NullPointerException if event is null
     */
    private void handleShowRules(@NotNull SlashCommandInteractionEvent event) {
        Objects.requireNonNull(event, "event must not be null");
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

    /**
     * Refreshes guild rules by fetching the latest messages from the configured rules channel.
     *
     * <p>If no rules channel is configured, returns the existing cached rules. Parses message 
     * content and embeds from the rules channel and updates the database with the result. 
     * Returns null if the rules channel is not configured or cannot be accessed.
     *
     * @param guild the guild to refresh rules for. Must not be null.
     * @param guildId the guild ID. Must not be null.
     * @return the refreshed guild rules, or null if rules channel is not configured
     * @throws NullPointerException if guild or guildId is null
     */
    @Nullable
    private GuildRules refreshRulesFromDiscord(@NotNull Guild guild, @NotNull GuildID guildId) {
        Objects.requireNonNull(guild, "guild must not be null");
        Objects.requireNonNull(guildId, "guildId must not be null");
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

    /**
     * Fetches and concatenates rule text from messages in the specified rules channel.
     *
     * <p>Retrieves up to 100 messages from the rules channel, extracts text from message 
     * content and embeds, and combines them. Returns null if the channel is not a text 
     * channel or if a network error occurs.
     *
     * @param guild the guild containing the rules channel. Must not be null.
     * @param rulesChannelId the ID of the rules channel. Must not be null.
     * @return concatenated rules text from the channel, or null if unable to fetch
     * @throws NullPointerException if guild or rulesChannelId is null
     */
    @Nullable
    private String fetchRulesTextFromChannel(@NotNull Guild guild, @NotNull ChannelID rulesChannelId) {
        Objects.requireNonNull(guild, "guild must not be null");
        Objects.requireNonNull(rulesChannelId, "rulesChannelId must not be null");
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

    /**
     * Extracts displayable text from a Discord message.
     *
     * <p>Combines message content and parsed embed text. If both are present, joins them 
     * with a newline. Returns the available text or an empty string if neither is present.
     *
     * @param message the message to extract text from. Must not be null.
     * @return the extracted text, or empty string if no content
     * @throws NullPointerException if message is null
     */
    @NotNull
    private String extractRuleText(@NotNull Message message) {
        Objects.requireNonNull(message, "message must not be null");
        String content = message.getContentDisplay();
        String embed = EmbedParser.parseEmbed(message);

        boolean hasContent = !content.isBlank();
        boolean hasEmbed = !embed.isBlank();

        if (hasContent && hasEmbed) {
            return content + "\n" + embed;
        }
        if (hasContent) {
            return content;
        }
        return hasEmbed ? embed : "";
    }

    /**
     * Handles the purge subcommand.
     *
     * <p>Deletes a specified text channel and immediately recreates it with the same 
     * name, position, and topic. Useful for clearing channel history. Replies with 
     * success/failure status via ephemeral message. The interaction is acknowledged 
     * before deletion to prevent timeout.
     *
     * @param event the slash command interaction event. Must not be null.
     * @throws NullPointerException if event is null
     */
    private void handlePurge(@NotNull SlashCommandInteractionEvent event) {
        Objects.requireNonNull(event, "event must not be null");
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
                ignored -> {
                    assert guild != null;
                    guild.createTextChannel(channelName)
                            .setPosition(position)
                            .setTopic(topic)
                            .queue(
                                ignoredChannel -> logger.debug("Purged channel: {} in guild: {}", channelName, guild.getId()),
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