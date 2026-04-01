package net.honeyberries.message;

import net.dv8tion.jda.api.entities.Member;
import net.dv8tion.jda.api.entities.Message;
import org.jetbrains.annotations.NotNull;

import java.util.Objects;

/**
 * Centralized filters for deciding whether Discord messages should be considered for context or moderation.
 * Keeps the inclusion rules consistent across fetchers and processors, reducing duplicate predicate logic.
 */
public class MessageFilter {

    private MessageFilter() {
        // utility class
    }

    /**
     * Determines if a message should be included when building conversational context for the AI.
     * Excludes system messages, webhooks, and voice messages to avoid polluting context with bot/system traffic.
     *
     * @param message message to inspect; must not be {@code null}
     * @return {@code true} if the message is a non-system guild message suitable for context windows
     * @throws NullPointerException if {@code message} is {@code null}
     */
    public static boolean shouldIncludeMessageForContext(@NotNull Message message) {
        Objects.requireNonNull(message, "message must not be null");
        return !message.getAuthor().isSystem()
                && message.isFromGuild()
                && !message.isWebhookMessage()
                && !message.isVoiceMessage();
    }

    /**
     * Determines if a message should be excluded from moderation processing.
     * Requires a guild member author and excludes webhook and voice messages to focus on user-generated text.
     *
     * @param message message to inspect; must not be {@code null}
     * @return {@code true} if the message comes from a guild member and is not eligible for moderation
     * @throws NullPointerException if {@code message} is {@code null}
     */
    public static boolean shouldExcludeMessageForModeration(@NotNull Message message) {
        Objects.requireNonNull(message, "message must not be null");
        return !(message.getAuthor() instanceof Member)
                || !message.isFromGuild()
                || message.isVoiceMessage()
                || message.isWebhookMessage()
                || message.isEphemeral();
    }
}
