package net.honeyberries.message;

import net.dv8tion.jda.api.entities.Message;
import net.dv8tion.jda.api.entities.channel.concrete.TextChannel;
import net.honeyberries.config.AppConfig;
import net.honeyberries.datatypes.content.ModerationMessage;
import net.honeyberries.datatypes.discord.MessageID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.*;
import java.util.concurrent.CompletableFuture;

public class HistoryFetcher {

    private static final Logger logger = LoggerFactory.getLogger(HistoryFetcher.class);

    /**
     * Fetches messages in the HISTORY CONTEXT window only (background context for AI).
     * Window: [now - maxAge, now - queueDuration]
     * <p>
     * These messages are fetched when the queue triggers to provide background context
     * to the AI about older conversations. They are NOT the primary messages being moderated.
     */
    public static CompletableFuture<List<ModerationMessage>> fetchHistoryContextMessages(
            TextChannel channel,
            List<MessageID> currentMessageIds
    ) {
        double maxAgeSeconds = AppConfig.getInstance().getHistoryContextMaxAge();
        double queueDurationSeconds = AppConfig.getInstance().getModerationQueueDuration();
        int msgLimit = Math.toIntExact(AppConfig.getInstance().getHistoryContextMaxMessages());

        long maxAgeMillis = Math.round(maxAgeSeconds * 1000);
        long queueDurationMillis = Math.round(queueDurationSeconds * 1000);
        
        Duration maxAge = Duration.ofMillis(maxAgeMillis);
        Duration queueDuration = Duration.ofMillis(queueDurationMillis);

        OffsetDateTime cutoffOld = OffsetDateTime.now().minus(maxAge);
        OffsetDateTime cutoffNew = OffsetDateTime.now().minus(queueDuration);

        Set<MessageID> seen = new HashSet<>(currentMessageIds);

        return channel.getHistory()
                .retrievePast(msgLimit)
                .submit()
                .thenApply(messages -> {
                    List<ModerationMessage> result = new ArrayList<>();

                    for (Message msg : messages) {
                        OffsetDateTime msgTime = msg.getTimeCreated();

                        // Stop if we've gone too far back (past HISTORY CONTEXT window)
                        if (msgTime.isBefore(cutoffOld)) {
                            break;
                        }

                        // Skip if message is in NOW window (too recent for history context)
                        if (!msgTime.isBefore(cutoffNew)) {
                            continue;
                        }

                        MessageID id = MessageID.fromMessage(msg);

                        if (seen.contains(id)) continue;
                        if (!MessageFilter.shouldIncludeMessageForContext(msg)) continue;

                        boolean hasText = !msg.getContentDisplay().isBlank();
                        boolean hasMedia = !msg.getAttachments().isEmpty() || !msg.getEmbeds().isEmpty();

                        if (!hasText && !hasMedia) continue;

                        result.add(ModerationMessage.fromMessage(msg, true).markAsHistory());
                    }

                    Collections.reverse(result);
                    return result;
                })
                .exceptionally(e -> {
                    logger.warn("Failed to fetch history context for channel {}: {}", channel.getId(), e.getMessage());
                    return List.of();
                });
    }


    /**
     * ============== THREE TIME WINDOWS ==============
     *
     * 1. PAST HISTORY:         [far past, now - maxAge]
     *    → Too old, ignore/archive
     *
     * 2. HISTORY CONTEXT:      [now - maxAge, now - queueDuration]
     *    → Background context for AI (fetched when queue triggers)
     *
     * 3. NOW (Current Queue):  [now - queueDuration, now]
     *    → Fresh messages accumulated during queue wait
     *
     * When queue triggers: send HISTORY CONTEXT + NOW to AI for moderation
     * ================================================
     */

    /**
     * Checks if message is within the active context window (recent, usable for AI context).
     * Window: [cutoff (now - maxAge), now]
     * This is HISTORY CONTEXT + NOW combined.
     */
    public static boolean isInCurrentContextWindow(Message message) {
        double maxAgeSeconds = AppConfig.getInstance().getHistoryContextMaxAge();
        long millis = Math.round(maxAgeSeconds * 1000);
        Duration maxAge = Duration.ofMillis(millis);
        OffsetDateTime cutoff = OffsetDateTime.now().minus(maxAge);

        return !message.getTimeCreated().isBefore(cutoff);
    }

    /**
     * Checks if message is in the past history (older than the context window, too old to use).
     * Window: [far past, now - maxAge]
     */
    public static boolean isPastHistoryWindow(Message message) {
        return !isInCurrentContextWindow(message);
    }

    /**
     * Checks if message is in the HISTORY CONTEXT window (background context for AI).
     * Window: [now - maxAge, now - queueDuration]
     * <p>
     * These are messages BEFORE the current queue period started.
     * Useful for providing context to the AI about older conversations.
     */
    public static boolean isInHistoryContextWindow(Message message) {
        double maxAgeSeconds = AppConfig.getInstance().getHistoryContextMaxAge();
        double queueDurationSeconds = AppConfig.getInstance().getModerationQueueDuration();
        
        long maxAgeMillis = Math.round(maxAgeSeconds * 1000);
        long queueDurationMillis = Math.round(queueDurationSeconds * 1000);
        
        Duration maxAge = Duration.ofMillis(maxAgeMillis);
        Duration queueDuration = Duration.ofMillis(queueDurationMillis);
        
        OffsetDateTime cutoffOld = OffsetDateTime.now().minus(maxAge);
        OffsetDateTime cutoffNew = OffsetDateTime.now().minus(queueDuration);
        
        OffsetDateTime msgTime = message.getTimeCreated();
        return !msgTime.isBefore(cutoffOld) && msgTime.isBefore(cutoffNew);
    }

    /**
     * Checks if message is in the NOW window (current queue period).
     * Window: [now - queueDuration, now]
     * 
     * These are fresh messages that have accumulated while the queue was waiting.
     * These are the primary messages to be moderated.
     */
    public static boolean isInNowWindow(Message message) {
        double queueDurationSeconds = AppConfig.getInstance().getModerationQueueDuration();
        long queueDurationMillis = Math.round(queueDurationSeconds * 1000);
        Duration queueDuration = Duration.ofMillis(queueDurationMillis);
        
        OffsetDateTime cutoff = OffsetDateTime.now().minus(queueDuration);
        return !message.getTimeCreated().isBefore(cutoff);
    }

}