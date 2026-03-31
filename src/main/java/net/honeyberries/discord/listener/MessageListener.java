package net.honeyberries.discord.listener;

import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.events.message.MessageDeleteEvent;
import net.dv8tion.jda.api.events.message.MessageReceivedEvent;
import net.dv8tion.jda.api.events.message.MessageUpdateEvent;
import net.dv8tion.jda.api.hooks.ListenerAdapter;
import net.honeyberries.datatypes.discord.MessageID;
import net.honeyberries.message.HistoryFetcher;
import net.honeyberries.message.MessageFilter;
import net.honeyberries.services.GlobalOrchestrationService;
import org.jetbrains.annotations.NotNull;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class MessageListener extends ListenerAdapter {

    Logger logger = LoggerFactory.getLogger(MessageListener.class);

    @Override
    public void onMessageReceived(@NotNull MessageReceivedEvent event) {
        logger.debug("Received message: {}", event.getMessage().getContentDisplay());

        if (!MessageFilter.shouldIncludeMessageForModeration(event.getMessage())) {
            return;
        }

        Guild guild = event.getGuild();

        GlobalOrchestrationService.getInstance().addMessage(guild, event.getMessage(), false);

    }


    @Override
    public void onMessageUpdate(@NotNull MessageUpdateEvent event) {
        logger.debug("Edited message: {}", event.getMessage().getContentDisplay());

        if (!MessageFilter.shouldIncludeMessageForModeration(event.getMessage())) {
            return;
        }

        boolean shouldBeUpdated = HistoryFetcher.isInCurrentContextWindow(event.getMessage());

        Guild guild = event.getGuild();

        if (shouldBeUpdated) {
            logger.debug("Message is in current context window. Updating message.");
            GlobalOrchestrationService.getInstance().updateMessage(guild, event.getMessage(), false);
        }

    }

    @Override
    public void onMessageDelete(@NotNull MessageDeleteEvent event) {
        logger.debug("Deleted message ID: {}", event.getMessageId());

        MessageID messageID = new MessageID(event.getMessageIdLong());
        Guild guild = event.getGuild();

        GlobalOrchestrationService.getInstance().removeMessage(guild, messageID);
    }

}
