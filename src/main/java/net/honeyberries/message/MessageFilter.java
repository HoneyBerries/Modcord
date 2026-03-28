package net.honeyberries.message;

import net.dv8tion.jda.api.entities.Member;
import net.dv8tion.jda.api.entities.Message;

public class MessageFilter {

    public static boolean shouldIncludeMessageForContext(Message message) {
        // Filter out messages from bots (including itself)
        return !message.getAuthor().isSystem()
                && message.isFromGuild()
                && !message.isWebhookMessage()
                && !message.isVoiceMessage();
    }


    public static boolean shouldIncludeMessageForModeration(Message message) {
        return message.getAuthor() instanceof Member
                && message.isFromGuild()
                && !message.isVoiceMessage()
                && !message.isWebhookMessage();
    }



}
