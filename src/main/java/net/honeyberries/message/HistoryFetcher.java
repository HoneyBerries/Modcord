package net.honeyberries.message;

import net.dv8tion.jda.api.entities.Message;
import net.dv8tion.jda.api.entities.channel.concrete.TextChannel;
import net.honeyberries.config.AppConfig;
import net.honeyberries.datatypes.content.ModerationMessage;
import net.honeyberries.datatypes.discord.MessageID;
import org.jetbrains.annotations.NotNull;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.*;
import java.util.concurrent.CompletableFuture;

/**
 * Retrieves historical Discord messages for context-aware moderation.
 * Exposes helper predicates for the three moderation windows (past, history context, now) and a bulk fetcher for context messages.
 */
public class HistoryFetcher {

    private static final Logger logger = LoggerFactory.getLogger(HistoryFetcher.class);

    /**
     * Fetches messages in the HISTORY CONTEXT window only (background context for AI).
     * Window: [now - maxAge, now - queueDuration]
     * <p>
     * These messages are fetched when the queue triggers to provide background context
     * to the AI about older conversations. They are NOT the primary messages being moderated.
     *
     * @param channel            text channel to retrieve from; must not be {@code null}
     * @param currentMessageIds  identifiers already queued in the current batch to avoid duplicates; must not be {@code null}
     * @return future containing context messages in chronological order (or empty list on failure)
     */
    public static @NotNull CompletableFuture<List<ModerationMessage>> fetchHistoryContextMessages(
            @NotNull TextChannel channel,
            @NotNull List<MessageID> currentMessageIds
    ) {
        Objects.requireNonNull(channel, "channel must not be null");
        Objects.requireNonNull(currentMessageIds, "currentMessageIds must not be null");
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
                        continue;
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


    /*
      ============== THREE TIME WINDOWS ==============

      1. PAST HISTORY:         [far past, now - maxAge]
         → Too old, ignore/archive

      2. HISTORY CONTEXT:      [now - maxAge, now - queueDuration]
         → Background context for AI (fetched when queue triggers)

      3. NOW (Current Queue):  [now - queueDuration, now]
         → Fresh messages accumulated during queue wait

      When queue triggers: send HISTORY CONTEXT + NOW to AI for moderation
      ================================================
     */

    /**
     * Checks if message is within the active context window (recent, usable for AI context).
     * Window: [cutoff (now - maxAge), now]
     * This is HISTORY CONTEXT + NOW combined.
     *
     * @param message message to evaluate; must not be {@code null}
     * @return {@code true} if the message is recent enough for consideration
     */
    public static boolean isInCurrentContextWindow(@NotNull Message message) {
        Objects.requireNonNull(message, "message must not be null");
        double maxAgeSeconds = AppConfig.getInstance().getHistoryContextMaxAge();
        long millis = Math.round(maxAgeSeconds * 1000);
        Duration maxAge = Duration.ofMillis(millis);
        OffsetDateTime cutoff = OffsetDateTime.now().minus(maxAge);

        return !message.getTimeCreated().isBefore(cutoff);
    }

    /**
     * Checks if message is in the past history (older than the context window, too old to use).
     * Window: [far past, now - maxAge]
     *
     * @param message message to evaluate; must not be {@code null}
     * @return {@code true} if the message is older than the maximum context age
     */
    public static boolean isPastHistoryWindow(@NotNull Message message) {
        Objects.requireNonNull(message, "message must not be null");
        return !isInCurrentContextWindow(message);
    }

    /**
     * Checks if message is in the HISTORY CONTEXT window (background context for AI).
     * Window: [now - maxAge, now - queueDuration]
     * <p>
     * These are messages BEFORE the current queue period started.
     * Useful for providing context to the AI about older conversations.
     *
     * @param message message to evaluate; must not be {@code null}
     * @return {@code true} if the message falls in the history context window
     */
    public static boolean isInHistoryContextWindow(@NotNull Message message) {
        Objects.requireNonNull(message, "message must not be null");
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
     * <p>
     * These are fresh messages that have accumulated while the queue was waiting.
     * These are the primary messages to be moderated.
     *
     * @param message message to evaluate; must not be {@code null}
     * @return {@code true} if the message falls in the current queue window
     */
    public static boolean isInNowWindow(@NotNull Message message) {
        Objects.requireNonNull(message, "message must not be null");
        double queueDurationSeconds = AppConfig.getInstance().getModerationQueueDuration();
        long queueDurationMillis = Math.round(queueDurationSeconds * 1000);
        Duration queueDuration = Duration.ofMillis(queueDurationMillis);

        OffsetDateTime cutoff = OffsetDateTime.now().minus(queueDuration);
        return !message.getTimeCreated().isBefore(cutoff);
    }

}
