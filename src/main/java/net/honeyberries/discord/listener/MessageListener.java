package net.honeyberries.discord.listener;

import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.Member;
import net.dv8tion.jda.api.entities.User;
import net.dv8tion.jda.api.entities.channel.middleman.MessageChannel;
import net.dv8tion.jda.api.events.message.MessageDeleteEvent;
import net.dv8tion.jda.api.events.message.MessageReceivedEvent;
import net.dv8tion.jda.api.events.message.MessageUpdateEvent;
import net.dv8tion.jda.api.hooks.ListenerAdapter;
import net.honeyberries.database.repository.ExcludedEntitiesRepository;
import net.honeyberries.datatypes.discord.*;
import net.honeyberries.datatypes.preferences.GuildPreferences;
import net.honeyberries.message.HistoryFetcher;
import net.honeyberries.message.MessageFilter;
import net.honeyberries.preferences.PreferencesManager;
import net.honeyberries.services.GlobalOrchestrationService;
import org.jetbrains.annotations.NotNull;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.List;

/**
 * Listens to Discord message events (received, updated, deleted) and routes them to the moderation orchestration layer.
 * Filters out system messages, bot messages, and excluded users before processing.
 * Maintains a rolling context window of recent messages for moderation decisions.
 */
public class MessageListener extends ListenerAdapter {

    /** Logger for message event details. */
    private final Logger logger = LoggerFactory.getLogger(MessageListener.class);
    /** Repository for managing exclusion lists. */
    private final ExcludedEntitiesRepository excludedEntitiesRepository = ExcludedEntitiesRepository.getInstance();
    /** Orchestration service coordinating per-guild moderation message queues. */
    private final GlobalOrchestrationService globalOrchestrationService = GlobalOrchestrationService.getInstance();
    /** Manager for guild preference lookups. */
    private final PreferencesManager preferencesManager = PreferencesManager.getInstance();

    /**
     * Identifiers extracted from a Discord message event, bundled together so the same
     * extraction logic can be shared between {@link #onMessageReceived(MessageReceivedEvent)}
     * and {@link #onMessageUpdate(MessageUpdateEvent)}.
     *
     * @param guildID  the guild the message was sent in
     * @param userID   the author of the message
     * @param roles    the roles held by the author at the time of the event
     * @param channelID the channel the message was sent in
     */
    private record MessageContext(@NotNull GuildID guildID, @NotNull UserID userID, @NotNull List<RoleID> roles, @NotNull ChannelID channelID) {}

    /**
     * Extracts the guild, user, role, and channel identifiers relevant to moderation filtering
     * from a message event's constituent parts.
     *
     * @param guild   the guild the message was sent in; must not be {@code null}
     * @param author  the author of the message; must not be {@code null}
     * @param member  the guild member corresponding to the author; must not be {@code null}
     * @param channel the channel the message was sent in; must not be {@code null}
     * @return a {@link MessageContext} bundling the extracted identifiers
     */
    private static MessageContext extractIds(@NotNull Guild guild, @NotNull User author, @NotNull Member member, @NotNull MessageChannel channel) {
        GuildID guildID = GuildID.fromGuild(guild);
        UserID userID = UserID.fromUser(author);
        List<RoleID> roleIDList = RoleID.fromRoles(member.getRoles());
        ChannelID channelID = ChannelID.fromChannel(channel);
        return new MessageContext(guildID, userID, roleIDList, channelID);
    }


    /**
     * Processes newly received messages for potential moderation violations.
     * Filters out messages from bots, system messages, and excluded users, then enqueues the message for batch evaluation.
     *
     * @param event the message received event from Discord
     * @throws NullPointerException if {@code event} is {@code null}
     */
    @Override
    public void onMessageReceived(@NotNull MessageReceivedEvent event) {
        logger.debug("Received message: {}", event.getMessage().getContentDisplay());

        if (MessageFilter.shouldExcludeMessageForModeration(event.getMessage())) {
            return;
        }

        Guild guild = event.getGuild();
        MessageContext context = extractIds(guild, event.getAuthor(), event.getMember(), event.getChannel());

        if (shouldExclude(context.guildID(), context.userID(), context.roles(), context.channelID())) {
            logger.debug("Message excluded by filter upon receiving. Not adding to context window.");
            return;
        }

        globalOrchestrationService.addMessage(guild, event.getMessage(), false);
    }

    /**
     * Processes edited messages by determining if they fall within the current context window.
     * If recent enough, replaces the original message in the context window with the updated content.
     * Respects the same filtering rules as {@link #onMessageReceived(MessageReceivedEvent)}.
     *
     * @param event the message update event from Discord
     * @throws NullPointerException if {@code event} is {@code null}
     */
    @Override
    public void onMessageUpdate(@NotNull MessageUpdateEvent event) {
        logger.debug("Edited message: {}", event.getMessage().getContentDisplay());

        if (MessageFilter.shouldExcludeMessageForModeration(event.getMessage())) {
            return;
        }

        boolean shouldBeUpdated = HistoryFetcher.isInCurrentContextWindow(event.getMessage());

        Guild guild = event.getGuild();
        MessageContext context = extractIds(guild, event.getAuthor(), event.getMember(), event.getChannel());

        if (shouldExclude(context.guildID(), context.userID(), context.roles(), context.channelID())) {
            logger.debug("Message excluded by filter upon editing. Not adding to context window.");
            return;
        }


        if (shouldBeUpdated) {
            logger.debug("Message is in current context window. Updating message.");
            globalOrchestrationService.updateMessage(guild, event.getMessage(), false);
        }

    }

    /**
     * Processes message deletions by removing the message from the context window.
     * This prevents evaluation of deleted messages during moderation decisions.
     *
     * @param event the message delete event from Discord
     * @throws NullPointerException if {@code event} is {@code null}
     */
    @Override
    public void onMessageDelete(@NotNull MessageDeleteEvent event) {
        logger.debug("Deleted message ID: {}", event.getMessageId());

        MessageID messageID = new MessageID(event.getMessageIdLong());
        Guild guild = event.getGuild();
        if (guild == null) {
            return;
        }

        GuildID guildID = GuildID.fromGuild(guild);
        GuildPreferences prefs = preferencesManager.getOrDefaultPreferences(guildID);

        if (prefs.removeOnDeleteEnabled()) {
            globalOrchestrationService.removeMessage(guild, messageID);
        }
    }
    
    
    
    /**
     * Determines if a user, channel, or any of the roles within a guild should be excluded
     * based on the exclusion settings in the {@code ExcludedEntitiesRepository}.
     *
     * @param guildID the identifier of the guild where the exclusions are checked; must not be {@code null}
     * @param userID the identifier of the user being checked for exclusion; must not be {@code null}
     * @param roleIDList a list of role identifiers to check for exclusion; must not be {@code null}
     * @param channelID the identifier of the channel being checked for exclusion; must not be {@code null}
     * @return {@code true} if the user, any role, or the channel is excluded in the specified guild; {@code false} otherwise
     */
    public boolean shouldExclude(@NotNull GuildID guildID, @NotNull UserID userID, @NotNull List<RoleID> roleIDList, @NotNull ChannelID channelID) {

        boolean excludeUser = excludedEntitiesRepository.isExcluded(guildID, userID);
        boolean excludeChannel = excludedEntitiesRepository.isExcluded(guildID, channelID);
        boolean excludeRoles = roleIDList.stream().anyMatch(roleID -> excludedEntitiesRepository.isExcluded(guildID, roleID));

        return excludeUser || excludeChannel || excludeRoles;
    }
    

}
