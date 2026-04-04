package net.honeyberries.discord.listener;

import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.events.message.MessageDeleteEvent;
import net.dv8tion.jda.api.events.message.MessageReceivedEvent;
import net.dv8tion.jda.api.events.message.MessageUpdateEvent;
import net.dv8tion.jda.api.hooks.ListenerAdapter;
import net.honeyberries.database.ExcludedUsersRepository;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.discord.MessageID;
import net.honeyberries.datatypes.discord.RoleID;
import net.honeyberries.datatypes.discord.UserID;
import net.honeyberries.message.HistoryFetcher;
import net.honeyberries.message.MessageFilter;
import net.honeyberries.services.GlobalOrchestrationService;
import org.jetbrains.annotations.NotNull;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Listens to Discord message events (received, updated, deleted) and routes them to the moderation orchestration layer.
 * Filters out system messages, bot messages, and excluded users before processing.
 * Maintains a rolling context window of recent messages for moderation decisions.
 */
public class MessageListener extends ListenerAdapter {

    /** Logger for message event details. */
    private final Logger logger = LoggerFactory.getLogger(MessageListener.class);
    /** Repository for checking user exclusion lists. */
    private final ExcludedUsersRepository excludedUsersRepository = ExcludedUsersRepository.getInstance();

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
        if (event.getMember() == null) {
            return;
        }

        if (excludedUsersRepository.isExcluded(
                GuildID.fromGuild(guild),
                new UserID(event.getAuthor().getIdLong()),
                event.getMember().getRoles().stream().map(role -> new RoleID(role.getIdLong())).toList()
        )) {
            return;
        }

        GlobalOrchestrationService.getInstance().addMessage(guild, event.getMessage(), false);

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
        if (event.getMember() == null) {
            return;
        }

        if (excludedUsersRepository.isExcluded(
                GuildID.fromGuild(guild),
                new UserID(event.getAuthor().getIdLong()),
                event.getMember().getRoles().stream().map(role -> new RoleID(role.getIdLong())).toList()
        )) {
            return;
        }

        if (shouldBeUpdated) {
            logger.debug("Message is in current context window. Updating message.");
            GlobalOrchestrationService.getInstance().updateMessage(guild, event.getMessage(), false);
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

        GlobalOrchestrationService.getInstance().removeMessage(guild, messageID);
    }

}
