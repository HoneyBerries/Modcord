package net.honeyberries.services;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.openai.models.ResponseFormatJsonSchema;
import com.openai.models.chat.completions.ChatCompletionMessageParam;
import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.Member;
import net.dv8tion.jda.api.entities.Message;
import net.dv8tion.jda.api.entities.channel.Channel;
import net.dv8tion.jda.api.entities.channel.concrete.TextChannel;
import net.honeyberries.action.ActionHandler;
import net.honeyberries.ai.*;
import net.honeyberries.config.AppConfig;
import net.honeyberries.database.GuildModerationActionsRepository;
import net.honeyberries.datatypes.action.ActionData;
import net.honeyberries.datatypes.content.ModerationMessage;
import net.honeyberries.datatypes.content.ModerationUser;
import net.honeyberries.datatypes.content.ModerationUserChannel;
import net.honeyberries.datatypes.content.GuildModerationBatch;
import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.DiscordUsername;
import net.honeyberries.datatypes.discord.MessageID;
import net.honeyberries.datatypes.discord.UserID;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.message.HistoryFetcher;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.*;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutionException;
import java.util.stream.Collectors;

public class GuildMessageProcessingService {

    private final Logger logger = LoggerFactory.getLogger(GuildMessageProcessingService.class);

    private final Guild guild;
    private final GuildID guildId;

    // Message queue state
    private final Map<MessageID, ModerationMessage> messages = new ConcurrentHashMap<>();
    private final Map<MessageID, OffsetDateTime> arrivalTimes = new ConcurrentHashMap<>();

    public GuildMessageProcessingService(Guild guild) {
        this.guild = guild;
        this.guildId = GuildID.fromGuild(guild);
    }

    // -------------------------------------------------------------------------
    // Queue management
    // -------------------------------------------------------------------------

    public void addMessage(Message message, boolean isHistory) {
        ModerationMessage msg = ModerationMessage.fromMessage(message, isHistory);
        messages.put(msg.messageId(), msg);
        arrivalTimes.put(msg.messageId(), OffsetDateTime.now());
        logger.debug("Added message {} to guild {}", msg.messageId(), guildId);
    }

    public void updateMessage(Message message, boolean isHistory) {
        ModerationMessage msg = ModerationMessage.fromMessage(message, isHistory);
        messages.put(msg.messageId(), msg);
        arrivalTimes.putIfAbsent(msg.messageId(), OffsetDateTime.now());
        logger.debug("Updated message {} in guild {}", msg.messageId(), guildId);
    }

    public void removeMessage(MessageID messageId) {
        messages.remove(messageId);
        arrivalTimes.remove(messageId);
        logger.debug("Removed message {} from guild {}", messageId, guildId);
    }

    public boolean isQueueEmpty() {
        return messages.isEmpty();
    }

    // -------------------------------------------------------------------------
    // Queue windowing
    // -------------------------------------------------------------------------

    /** Fresh messages in [now - queueDuration, now]. */
    public List<ModerationMessage> getCurrentMessages() {
        OffsetDateTime cutoff = OffsetDateTime.now().minus(
                secondsToDuration(AppConfig.getInstance().getModerationQueueDuration()));
        return getMessagesBetween(cutoff, null);
    }

    /** Background context messages in [now - maxAge, now - queueDuration]. */
    public List<ModerationMessage> getHistoryContextMessages() {
        OffsetDateTime now = OffsetDateTime.now();
        OffsetDateTime from = now.minus(secondsToDuration(AppConfig.getInstance().getHistoryContextMaxAge()));
        OffsetDateTime to   = now.minus(secondsToDuration(AppConfig.getInstance().getModerationQueueDuration()));
        return getMessagesBetween(from, to);
    }

    private List<ModerationMessage> getMessagesBetween(OffsetDateTime from, OffsetDateTime to) {
        List<ModerationMessage> snapshot = new ArrayList<>(messages.values());
        return snapshot.stream()
                .filter(msg -> {
                    OffsetDateTime t = arrivalTime(msg);
                    return !t.isBefore(from) && (to == null || t.isBefore(to));
                })
                .sorted(Comparator.comparing(this::arrivalTime))
                .toList();
    }

    private OffsetDateTime arrivalTime(ModerationMessage msg) {
        return arrivalTimes.getOrDefault(msg.messageId(), OffsetDateTime.now());
    }

    private static Duration secondsToDuration(double seconds) {
        return Duration.ofMillis(Math.round(seconds * 1000));
    }

    public void clearQueue() {
        messages.clear();
        arrivalTimes.clear();
    }

    public void removeMessages(Collection<MessageID> messageIds) {
        for (MessageID messageId : messageIds) {
            messages.remove(messageId);
            arrivalTimes.remove(messageId);
        }
    }

    // -------------------------------------------------------------------------
    // Processing
    // -------------------------------------------------------------------------

    /** Full pipeline: fetch context, call AI, apply actions. */
    public boolean runPipeline() {
        List<ModerationMessage> currentMessages = getQueuedMessagesSnapshot();
        if (currentMessages.isEmpty()) {
            logger.debug("Skipping AI pipeline for guild {} because queue is empty", guildId.value());
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

        // log actions to database
        actions.parallelStream().forEach(
                action -> GuildModerationActionsRepository.getInstance().
                addActionToDatabase(action));

        // Now handle the actions and then return true if success and false if failed.
        boolean success = actions.parallelStream()
            .map(ActionHandler.getInstance()::processAction)
            .reduce(true, Boolean::logicalAnd);

        removeMessages(processedIds);
        return success;
    }

    private List<ModerationMessage> getQueuedMessagesSnapshot() {
        List<ModerationMessage> snapshot = new ArrayList<>(messages.values());
        return snapshot.stream()
                .sorted(Comparator.comparing(this::arrivalTime))
                .toList();
    }

    private List<ActionData> getActionDataFromAI(List<ModerationMessage> currentMessages) {

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

        ChatCompletionMessageParam inputs;
        ChatCompletionMessageParam systemPrompt;
        ResponseFormatJsonSchema schema;
        String response;

        logger.info("Creating datastructures for AI Input");

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

        try {
            logger.info("Submitting moderation batch for guild {} to LLM", guildId.value());
            response = InferenceEngine.getInstance().generateResponse(List.of(systemPrompt, inputs), schema).get();
        } catch (ExecutionException | InterruptedException e) {
            logger.error("Failed to generate response for guild {}", guildId, e);
            return List.of();
        }

        if (response == null || response.isBlank()) {
            logger.warn("LLM returned empty response for guild {}", guildId.value());
            return List.of();
        }

        try {
            UserID moderatorId = UserID.fromUser(guild.getJDA().getSelfUser());
            return ActionDataJSONParser.getInstance().parse(response, guildId, moderatorId);
        } catch (JsonProcessingException e) {
            logger.error("Failed to parse AI response for guild {}", guildId, e);
            return List.of();
        }
    }

    private List<ModerationMessage> fetchHistoryContextFromDiscord(List<ModerationMessage> currentMessages) {
        List<MessageID> messageIds = currentMessages.stream()
                .map(ModerationMessage::messageId)
                .toList();

        List<CompletableFuture<List<ModerationMessage>>> futures = currentMessages.stream()
                .map(ModerationMessage::channelId)
                .distinct()
                .map(cid -> guild.getGuildChannelById(cid.value()))
                .filter(c -> c instanceof TextChannel)
                .map(c -> HistoryFetcher.fetchHistoryContextMessages((TextChannel) c, messageIds))
                .toList();

        List<ModerationMessage> allHistory = new ArrayList<>();
        try {
            CompletableFuture.allOf(futures.toArray(new CompletableFuture[0])).get();
            futures.forEach(f -> {
                try { allHistory.addAll(f.get()); }
                catch (Exception e) { logger.warn("Failed to retrieve history batch", e); }
            });
        } catch (InterruptedException e) {
            logger.warn("History fetch interrupted for guild {}", guildId);
            Thread.currentThread().interrupt();
        } catch (ExecutionException e) {
            logger.warn("History fetch failed for guild {}", guildId, e);
        }

        return allHistory;
    }

    private List<ModerationUser> buildModerationUsers(List<ModerationMessage> messages) {
        Map<UserID, Map<ChannelID, List<ModerationMessage>>> userChannelMap = new HashMap<>();
        for (ModerationMessage msg : messages) {
            userChannelMap
                    .computeIfAbsent(msg.userId(), k -> new HashMap<>())
                    .computeIfAbsent(msg.channelId(), k -> new ArrayList<>())
                    .add(msg);
        }

        List<ModerationUser> result = new ArrayList<>();
        for (Map.Entry<UserID, Map<ChannelID, List<ModerationMessage>>> userEntry : userChannelMap.entrySet()) {
            UserID userId = userEntry.getKey();
            Member member = guild.retrieveMemberById(userId.value()).complete();
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
                    new DiscordUsername(userId, member.getEffectiveName()),
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