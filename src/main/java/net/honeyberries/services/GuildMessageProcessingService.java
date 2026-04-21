package net.honeyberries.services;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.openai.models.ResponseFormatJsonSchema;
import com.openai.models.chat.completions.ChatCompletionAssistantMessageParam;
import com.openai.models.chat.completions.ChatCompletionMessageParam;
import com.openai.models.chat.completions.ChatCompletionSystemMessageParam;
import com.openai.models.chat.completions.ChatCompletionUserMessageParam;
import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.Member;
import net.dv8tion.jda.api.entities.Message;
import net.dv8tion.jda.api.entities.channel.Channel;
import net.dv8tion.jda.api.entities.channel.concrete.TextChannel;
import net.honeyberries.action.ActionHandler;
import net.honeyberries.ai.*;
import net.honeyberries.ai.InferenceEngine.InferenceException;
import net.honeyberries.config.AppConfig;
import net.honeyberries.database.AILogRepository;
import net.honeyberries.database.GuildModerationActionsRepository;
import net.honeyberries.datatypes.action.ActionData;
import net.honeyberries.datatypes.content.ModerationMessage;
import net.honeyberries.datatypes.content.ModerationUser;
import net.honeyberries.datatypes.content.ModerationUserChannel;
import net.honeyberries.datatypes.content.GuildModerationBatch;
import net.honeyberries.datatypes.discord.*;
import net.honeyberries.datatypes.preferences.GuildPreferences;
import net.honeyberries.message.HistoryFetcher;
import net.honeyberries.preferences.PreferencesManager;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.*;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.stream.Collectors;

/**
 * Processes moderation messages for a single guild through an AI-based pipeline.
 * Maintains a time-windowed queue of messages with arrival timestamps for determining
 * current vs. historical context. Implements the complete moderation workflow:
 * (1) collect current queued messages and historical context, (2) build guild moderation batch,
 * (3) invoke AI inference with constrained schema, (4) parse AI responses into actions,
 * (5) log actions to database, (6) apply actions via ActionHandler.
 * <p>
 * Additional safeguards compared to the original implementation:
 * <ul>
 *   <li><b>Deduplication</b> — duplicate message IDs (from network retries) are silently ignored
 *       at enqueue time so the same message is never evaluated twice.</li>
 *   <li><b>Backpressure</b> — the queue is capped at {@code AppConfig.getMaxQueueSizePerGuild()};
 *       when full, the oldest enqueued message is evicted with a warning.</li>
 *   <li><b>Timeouts on blocking Discord calls</b> — member lookups and history fetches use the
 *       configurable {@code AppConfig.getDiscordRequestTimeout()} instead of blocking forever.</li>
 * </ul>
 */
public class GuildMessageProcessingService {

    /** Logger for message queue lifecycle and processing pipeline. */
    private final Logger logger = LoggerFactory.getLogger(GuildMessageProcessingService.class);

    /** The Discord guild this service manages. */
    private final Guild guild;
    /** The guild's ID for logging. */
    private final GuildID guildId;

    /** Message queue state: all messages currently pending moderation. */
    private final Map<MessageID, ModerationMessage> messages = new ConcurrentHashMap<>();
    /** Arrival time of each message for time-windowing calculations. */
    private final Map<MessageID, OffsetDateTime> arrivalTimes = new ConcurrentHashMap<>();

    /**
     * Constructs the message processing service for a guild.
     *
     * @param guild the Discord guild this service manages (must not be {@code null})
     * @throws NullPointerException if {@code guild} is {@code null}
     */
    public GuildMessageProcessingService(@NotNull Guild guild) {
        this.guild = Objects.requireNonNull(guild, "guild must not be null");
        this.guildId = GuildID.fromGuild(guild);
    }

    // =========================================================================
    // Queue Management
    // =========================================================================

    /**
     * Adds a new message to the queue with the current timestamp.
     * <p>
     * If the message ID is already present (duplicate from a network retry), the call is a
     * no-op so the same content is never evaluated twice.
     * If the queue is at capacity, the oldest queued message is evicted to apply backpressure.
     *
     * @param message   the message to add (must not be {@code null})
     * @param isHistory {@code true} if this is historical context, {@code false} if current
     * @throws NullPointerException if {@code message} is {@code null}
     */
    public void addMessage(@NotNull Message message, boolean isHistory) {
        Objects.requireNonNull(message, "message must not be null");

        ModerationMessage msg = ModerationMessage.fromMessage(message, isHistory);

        // Deduplication: skip if already present
        if (messages.containsKey(msg.messageId())) {
            logger.debug("Duplicate message {} ignored for guild {}", msg.messageId(), guildId);
            return;
        }

        applyBackpressureIfNeeded();

        messages.put(msg.messageId(), msg);
        arrivalTimes.put(msg.messageId(), OffsetDateTime.now());
        logger.debug("Added message {} to guild {}", msg.messageId(), guildId);
    }

    /**
     * Updates an existing message in the queue, preserving its original arrival time.
     * Arrival time is not updated if the message was already present (uses putIfAbsent).
     *
     * @param message   the updated message (must not be {@code null})
     * @param isHistory {@code true} if this is historical context
     * @throws NullPointerException if {@code message} is {@code null}
     */
    public void updateMessage(@NotNull Message message, boolean isHistory) {
        Objects.requireNonNull(message, "message must not be null");

        ModerationMessage msg = ModerationMessage.fromMessage(message, isHistory);
        messages.put(msg.messageId(), msg);
        arrivalTimes.putIfAbsent(msg.messageId(), OffsetDateTime.now());
        logger.debug("Updated message {} in guild {}", msg.messageId(), guildId);
    }

    /**
     * Removes a message from the queue, including its arrival time.
     *
     * @param messageId the ID of the message to remove (must not be {@code null})
     * @throws NullPointerException if {@code messageId} is {@code null}
     */
    public void removeMessage(@NotNull MessageID messageId) {
        Objects.requireNonNull(messageId, "messageId must not be null");

        messages.remove(messageId);
        arrivalTimes.remove(messageId);
        logger.debug("Removed message {} from guild {}", messageId, guildId);
    }

    /**
     * Checks if the message queue is empty (no pending messages).
     *
     * @return {@code true} if no messages are queued
     */
    public boolean isQueueEmpty() {
        return messages.isEmpty();
    }

    /**
     * Evicts the oldest message in the queue when the per-guild size cap is reached.
     * Logs a warning so operators know the queue is under pressure rather than silently dropping data.
     */
    private void applyBackpressureIfNeeded() {
        int maxSize = AppConfig.getInstance().getMaxQueueSizePerGuild();
        if (messages.size() < maxSize) {
            return;
        }

        // Find the oldest message by arrival time and evict it
        arrivalTimes.entrySet().stream()
                .min(Map.Entry.comparingByValue())
                .map(Map.Entry::getKey)
                .ifPresent(oldest -> {
                    messages.remove(oldest);
                    arrivalTimes.remove(oldest);
                    logger.warn("Queue full for guild {} (max={}), evicted oldest message {}",
                            guildId, maxSize, oldest);
                });
    }

    // =========================================================================
    // Queue Windowing
    // =========================================================================

    /**
     * Retrieves fresh messages within the current moderation window.
     * Returns messages that arrived between [now - queueDuration, now].
     * Used to identify current messages subject to moderation.
     *
     * @return a list of current messages in chronological order (oldest first)
     */
    @NotNull
    public List<ModerationMessage> getCurrentMessages() {
        OffsetDateTime cutoff = OffsetDateTime.now().minus(
                secondsToDuration(AppConfig.getInstance().getModerationQueueDuration()));
        return getMessagesBetween(cutoff, null);
    }

    /**
     * Retrieves background context messages for historical trend analysis.
     * Returns messages that arrived between [now - maxAge, now - queueDuration].
     * Used to build user history for the AI to understand patterns.
     *
     * @return a list of historical context messages in chronological order
     */
    @NotNull
    public List<ModerationMessage> getHistoryContextMessages() {
        OffsetDateTime now = OffsetDateTime.now();
        OffsetDateTime from = now.minus(secondsToDuration(AppConfig.getInstance().getHistoryContextMaxAge()));
        OffsetDateTime to   = now.minus(secondsToDuration(AppConfig.getInstance().getModerationQueueDuration()));
        return getMessagesBetween(from, to);
    }

    /**
     * Filters and sorts messages within a time range.
     * Messages are included if their arrival time is in [from, to) (to is exclusive if provided).
     *
     * @param from the inclusive lower bound (must not be {@code null})
     * @param to   the exclusive upper bound, or {@code null} for no upper bound
     * @return a list of messages in chronological order
     * @throws NullPointerException if {@code from} is {@code null}
     */
    @NotNull
    private List<ModerationMessage> getMessagesBetween(
            @NotNull OffsetDateTime from,
            @Nullable OffsetDateTime to) {
        Objects.requireNonNull(from, "from must not be null");

        List<ModerationMessage> snapshot = new ArrayList<>(messages.values());
        return snapshot.stream()
                .filter(msg -> {
                    OffsetDateTime t = arrivalTime(msg);
                    return !t.isBefore(from) && (to == null || t.isBefore(to));
                })
                .sorted(Comparator.comparing(this::arrivalTime))
                .toList();
    }

    /**
     * Retrieves the arrival time for a message, falling back to current time if not recorded.
     *
     * @param msg the message (must not be {@code null})
     * @return the message's arrival timestamp
     * @throws NullPointerException if {@code msg} is {@code null}
     */
    @NotNull
    private OffsetDateTime arrivalTime(@NotNull ModerationMessage msg) {
        Objects.requireNonNull(msg, "msg must not be null");
        return arrivalTimes.getOrDefault(msg.messageId(), OffsetDateTime.now());
    }

    /**
     * Converts a duration in seconds to a {@code Duration} object via millisecond rounding.
     *
     * @param seconds the duration in seconds
     * @return the {@code Duration} object
     */
    @NotNull
    private static Duration secondsToDuration(double seconds) {
        return Duration.ofMillis(Math.round(seconds * 1000));
    }

    /**
     * Clears all messages and arrival times from the queue.
     */
    public void clearQueue() {
        messages.clear();
        arrivalTimes.clear();
    }

    /**
     * Removes multiple messages from the queue by their IDs.
     *
     * @param messageIds the IDs of messages to remove (must not be {@code null})
     * @throws NullPointerException if {@code messageIds} is {@code null}
     */
    public void removeMessages(@NotNull Collection<MessageID> messageIds) {
        Objects.requireNonNull(messageIds, "messageIds must not be null");

        for (MessageID messageId : messageIds) {
            messages.remove(messageId);
            arrivalTimes.remove(messageId);
        }
    }

    // =========================================================================
    // Processing Pipeline
    // =========================================================================

    /**
     * Executes the complete moderation pipeline:
     * (1) Gets current queued messages from the time window
     * (2) Fetches historical context from Discord for trend analysis
     * (3) Builds guild moderation batch with user details and messages
     * (4) Invokes AI inference with dynamic schema and system prompt
     * (5) Parses AI response into ActionData objects
     * (6) Persists actions to database
     * (7) Applies actions via ActionHandler (parallel execution)
     * (8) Removes processed messages from queue
     * <p>
     * Returns {@code true} if actions were taken, {@code false} if no actions resulted.
     * Handles all exceptions gracefully, returning {@code false} on any failure and logging details.
     *
     * @return {@code true} if actions were successfully applied, {@code false} if none/error
     */
    public boolean runPipeline() {
        List<ModerationMessage> currentMessages = getQueuedMessagesSnapshot();
        GuildPreferences guildPreferences = PreferencesManager.getInstance().getOrDefaultPreferences(guildId);

        if (currentMessages.isEmpty()) {
            logger.debug("Skipping AI pipeline for guild {} because queue is empty", guildId.value());
            return true;
        }

        if (!guildPreferences.aiEnabled()) {
            logger.debug("Skipping AI pipeline for guild {} because AI moderation is disabled", guildId.value());
            return true;
        }

        logger.info("Running AI pipeline for guild {} with {} queued messages", guildId.value(), currentMessages.size());

        List<ActionData> actions = getActionDataFromAI(currentMessages);
        Set<MessageID> processedIds = currentMessages.stream()
                .map(ModerationMessage::messageId)
                .collect(Collectors.toSet());

        if (actions.isEmpty()) {
            removeMessages(processedIds);
            return false;
        }

        // Persist actions to database
        actions.parallelStream().forEach(
                action -> GuildModerationActionsRepository.getInstance().addActionToDatabase(action));

        // Execute actions in parallel and aggregate success
        boolean success = actions.parallelStream()
                .map(ActionHandler.getInstance()::processAction)
                .reduce(true, Boolean::logicalAnd);

        removeMessages(processedIds);
        return success;
    }

    /**
     * Restores a previously persisted {@link ModerationMessage} directly into the queue without
     * applying backpressure or deduplication checks.
     * <p>
     * Only used by the persistent-queue restore path on startup. The message arrival time is
     * set to now so it is treated as a current-window message and processed on the next pipeline run.
     *
     * @param msg the message to restore, must not be {@code null}
     * @throws NullPointerException if {@code msg} is {@code null}
     */
    public void restoreMessage(@NotNull ModerationMessage msg) {
        Objects.requireNonNull(msg, "msg must not be null");
        messages.put(msg.messageId(), msg);
        arrivalTimes.put(msg.messageId(), OffsetDateTime.now());
        logger.debug("Restored persisted message {} into guild {} queue", msg.messageId(), guildId);
    }

    /**
     * Creates a public snapshot of the current queue sorted by arrival time (oldest first).
     * Used by the persistent-queue shutdown save path.
     *
     * @return a list of queued messages in chronological order
     */
    @NotNull
    public List<ModerationMessage> getQueuedMessagesSnapshot() {
        List<ModerationMessage> snapshot = new ArrayList<>(messages.values());
        return snapshot.stream()
                .sorted(Comparator.comparing(this::arrivalTime))
                .toList();
    }

    /**
     * Orchestrates AI inference on the current moderation batch.
     * Fetches historical context, builds moderation users, generates schema and prompts,
     * invokes AI, and parses the response into ActionData objects.
     * Returns an empty list on any error (logged with details).
     *
     * @param currentMessages the messages to evaluate (must not be {@code null})
     * @return a list of ActionData objects from the AI, or empty list on error
     * @throws NullPointerException if {@code currentMessages} is {@code null}
     */
    @NotNull
    private List<ActionData> getActionDataFromAI(@NotNull List<ModerationMessage> currentMessages) {
        Objects.requireNonNull(currentMessages, "currentMessages must not be null");

        List<ModerationMessage> historyMessages = fetchHistoryContextFromDiscord(currentMessages);

        List<ModerationUser> users        = buildModerationUsers(currentMessages);
        List<ModerationUser> historyUsers = buildModerationUsers(historyMessages);

        GuildModerationBatch batch = new GuildModerationBatch(
                guildId,
                guild.getName(),
                Map.of(),
                users,
                historyUsers
        );

        ChatCompletionUserMessageParam inputs;
        ChatCompletionSystemMessageParam systemPrompt;
        ResponseFormatJsonSchema schema;
        ChatCompletionAssistantMessageParam response;

        List<ChatCompletionMessageParam> conversation = new ArrayList<>();

        logger.info("Creating data structures for AI input for guild {}", guildId.value());

        try {
            inputs = GuildModerationBatchToAIInput.createMessageFromGuildModerationBatch(batch);
        } catch (GuildModerationBatchToAIInput.GuildModerationBatchSerializationException e) {
            logger.error("Failed to serialize guild moderation batch for guild {}", guildId, e);
            return List.of();
        }

        try {
            schema = DynamicSchemaGenerator.getInstance().createDynamicOutputSchema(batch);
        } catch (DynamicSchemaGenerator.DynamicSchemaGeneratorParseException e) {
            logger.error("Failed to generate dynamic schema for guild {}", guildId, e);
            return List.of();
        }

        try {
            systemPrompt = DynamicSystemPrompt.getInstance().createDynamicSystemPrompt(guildId);
        } catch (Exception e) {
            logger.error("Failed to generate dynamic system prompt for guild {}", guildId, e);
            return List.of();
        }

        conversation.add(ChatCompletionMessageParam.ofSystem(systemPrompt));
        conversation.add(ChatCompletionMessageParam.ofUser(inputs));

        try {
            long timeoutSecs = AppConfig.getInstance().getAIRequestTimeout();
            logger.info("Submitting moderation batch for guild {} to LLM", guildId.value());
            response = InferenceEngine.getInstance()
                    .generateResponse(conversation, schema)
                    .get(timeoutSecs, TimeUnit.SECONDS);
            conversation.add(ChatCompletionMessageParam.ofAssistant(response));
        } catch (TimeoutException e) {
            logger.error("AI inference timed out for guild {} after {}s",
                    guildId, AppConfig.getInstance().getAIRequestTimeout());
            return List.of();
        } catch (ExecutionException e) {
            Throwable cause = e.getCause();
            if (cause instanceof InferenceException) {
                logger.error("AI inference engine error for guild {}: {}", guildId, cause.getMessage());
            } else {
                logger.error("Unexpected error during AI inference for guild {}", guildId, e);
            }
            return List.of();
        } catch (InterruptedException e) {
            logger.warn("AI inference interrupted for guild {}", guildId);
            Thread.currentThread().interrupt();
            return List.of();
        }

        // Store the AI response in the database
        boolean saved = AILogRepository.getInstance().addLogEntry(guildId, conversation);
        if (!saved) {
            logger.error("Failed to store AI response for guild {}", guildId);
        }

        try {
            UserID moderatorId = UserID.fromUser(guild.getJDA().getSelfUser());
            return ActionDataJSONParser.getInstance().parse(response, guildId, moderatorId);
        } catch (JsonProcessingException e) {
            logger.error("Failed to parse AI response JSON for guild {}: {}", guildId, e.getOriginalMessage());
            return List.of();
        }
    }

    /**
     * Fetches historical message context from Discord for trend analysis.
     * For each channel represented in currentMessages, retrieves messages before the oldest current message
     * to provide historical context to the AI.
     * Per-channel fetch futures are given a bounded timeout ({@link AppConfig#getDiscordRequestTimeout()}
     * seconds) so a single slow channel cannot stall the entire batch.
     *
     * @param currentMessages the current moderation batch (must not be {@code null})
     * @return a list of historical messages, or empty list if all fetches fail
     * @throws NullPointerException if {@code currentMessages} is {@code null}
     */
    @NotNull
    private List<ModerationMessage> fetchHistoryContextFromDiscord(
            @NotNull List<ModerationMessage> currentMessages) {
        Objects.requireNonNull(currentMessages, "currentMessages must not be null");

        List<MessageID> messageIds = currentMessages.stream()
                .map(ModerationMessage::messageId)
                .toList();

        long timeoutSecs = AppConfig.getInstance().getDiscordRequestTimeout();

        List<CompletableFuture<List<ModerationMessage>>> futures = currentMessages.stream()
                .map(ModerationMessage::channelId)
                .distinct()
                .map(cid -> guild.getGuildChannelById(cid.value()))
                .filter(c -> c instanceof TextChannel)
                .map(c -> HistoryFetcher.fetchHistoryContextMessages((TextChannel) c, messageIds)
                        .orTimeout(timeoutSecs, TimeUnit.SECONDS)
                        .exceptionally(e -> {
                            logger.warn("History fetch timed out or failed for channel in guild {}: {}",
                                    guildId, e.getMessage());
                            return List.of();
                        }))
                .toList();

        List<ModerationMessage> allHistory = new ArrayList<>();
        for (CompletableFuture<List<ModerationMessage>> f : futures) {
            try {
                allHistory.addAll(f.get(timeoutSecs + 1, TimeUnit.SECONDS));
            } catch (TimeoutException e) {
                logger.warn("History fetch future timed out for guild {}", guildId);
            } catch (InterruptedException e) {
                logger.warn("History fetch interrupted for guild {}", guildId);
                Thread.currentThread().interrupt();
            } catch (ExecutionException e) {
                logger.warn("History fetch failed for guild {}: {}", guildId, e.getCause().getMessage());
            }
        }

        return allHistory;
    }

    /**
     * Builds rich moderation user objects from a list of messages.
     * Groups messages by user and channel, retrieves member details (roles, effective name),
     * and constructs {@code ModerationUser} objects with full channel/message context.
     * Skips members that cannot be retrieved (deleted users, permission issues).
     * Member lookups are bounded by {@link AppConfig#getDiscordRequestTimeout()} so a
     * single slow lookup cannot stall the entire batch build.
     *
     * @param messages the messages to organize into user objects (must not be {@code null})
     * @return a list of moderation users with message context
     * @throws NullPointerException if {@code messages} is {@code null}
     */
    @NotNull
    private List<ModerationUser> buildModerationUsers(@NotNull List<ModerationMessage> messages) {
        Objects.requireNonNull(messages, "messages must not be null");

        Map<UserID, Map<ChannelID, List<ModerationMessage>>> userChannelMap = new HashMap<>();
        for (ModerationMessage msg : messages) {
            userChannelMap
                    .computeIfAbsent(msg.userId(), k -> new HashMap<>())
                    .computeIfAbsent(msg.channelId(), k -> new ArrayList<>())
                    .add(msg);
        }

        long timeoutSecs = AppConfig.getInstance().getDiscordRequestTimeout();
        List<ModerationUser> result = new ArrayList<>();

        for (Map.Entry<UserID, Map<ChannelID, List<ModerationMessage>>> userEntry : userChannelMap.entrySet()) {
            UserID userId = userEntry.getKey();
            Member member;
            try {
                member = guild.retrieveMemberById(userId.value())
                        .timeout(timeoutSecs, TimeUnit.SECONDS)
                        .complete();
            } catch (Exception e) {
                logger.warn("Failed to retrieve member {} for guild {} within {}s: {}",
                        userId, guildId, timeoutSecs, e.getMessage());
                continue;
            }
            if (member == null) continue;

            List<ModerationUserChannel> channels = userEntry.getValue().entrySet().stream()
                    .map(e -> {
                        Channel channel = guild.getGuildChannelById(e.getKey().value());
                        String channelName = channel != null ? channel.getName() : "Unknown";
                        return new ModerationUserChannel(userId, e.getKey(), channelName, e.getValue());
                    })
                    .toList();

            List<String> roles = member.getRoles().stream()
                    .map(net.dv8tion.jda.api.entities.Role::getName)
                    .collect(Collectors.toList());

            result.add(new ModerationUser(
                    userId,
                    new DiscordUser(userId, member.getEffectiveName()),
                    member.getTimeJoined().toLocalDateTime(),
                    member,
                    guild,
                    roles,
                    channels
            ));
        }
        return result;
    }
}
