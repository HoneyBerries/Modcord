package net.honeyberries.ai;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.openai.models.chat.completions.ChatCompletionAssistantMessageParam;
import net.honeyberries.datatypes.action.ActionData;
import net.honeyberries.datatypes.action.ActionDataBuilder;
import net.honeyberries.datatypes.action.ActionType;
import net.honeyberries.datatypes.action.MessageDeletion;
import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.discord.MessageID;
import net.honeyberries.datatypes.discord.UserID;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.time.Instant;
import java.util.*;

/**
 * Parses JSON responses from the AI moderation model into ActionData objects.
 * Handles conversion of AI's JSON schema output (containing action types, reasons, durations, message deletions)
 * into type-safe, actionable {@code ActionData} objects for the moderation system.
 * Provides singleton access and detailed error messages for malformed AI responses.
 */
public class ActionDataJSONParser {

    /** Logger for parse operations and validation errors. */
    private static final Logger logger = LoggerFactory.getLogger(ActionDataJSONParser.class);
    /** JSON object mapper for parsing and tree traversal. */
    private static final ObjectMapper mapper = new ObjectMapper();
    /** Singleton instance. */
    private static final ActionDataJSONParser INSTANCE = new ActionDataJSONParser();

    /**
     * Maps AI's lowercase action type strings to {@code ActionType} enum values.
     * Supports: null (no action), delete, warn, timeout, kick, ban.
     * Case-insensitive; unknown values trigger {@code ActionDataParseException}.
     */
    private static final Map<String, ActionType> ACTION_TYPE_MAP = Map.of(
            "null",    ActionType.NULL,
            "delete",  ActionType.DELETE,
            "warn",    ActionType.WARN,
            "timeout", ActionType.TIMEOUT,
            "kick",    ActionType.KICK,
            "ban",     ActionType.BAN
    );

    private ActionDataJSONParser() {}

    /**
     * Retrieves the singleton instance of the parser.
     *
     * @return the singleton {@code ActionDataJSONParser}
     */
    @NotNull
    public static ActionDataJSONParser getInstance() {
        return INSTANCE;
    }

    /**
     * Parses the AI's JSON output into a list of {@code ActionData} objects.
     * Expects a JSON structure with a top-level "users" array, each containing action, reason, durations, and channels/deletions.
     * Creates a new {@code ActionData} instance per user with a random UUID.
     *
     * @param response the response object returned by the AI inference engine
     * @param guildId the guild context for the moderation actions (may be {@code null} in test scenarios)
     * @param moderatorId the ID of the moderator performing the actions (must not be {@code null})
     * @return a list of {@code ActionData} objects, one per user in the batch
     * @throws JsonProcessingException if the JSON cannot be parsed by Jackson
     * @throws ActionDataParseException if the JSON is malformed, missing required fields, or contains invalid action types
     * @throws NullPointerException if {@code json} or {@code moderatorId} is {@code null}
     */
    @NotNull
    public List<ActionData> parse(
            @NotNull ChatCompletionAssistantMessageParam response,
            @NotNull GuildID guildId,
            @NotNull UserID moderatorId)
            throws JsonProcessingException, ActionDataParseException {

        String json = response.content()
                .filter(ChatCompletionAssistantMessageParam.Content::isText)
                .map(ChatCompletionAssistantMessageParam.Content::asText)
                .orElse(null);

        if (json == null || json.isBlank()) {
            logger.error("Empty AI response received, returning empty ActionData list.");
            return List.of();
        }

        JsonNode root = mapper.readTree(json);
        return parseUsers(root.get("users"), guildId, moderatorId);
    }

    /**
     * Parses the "users" array from the AI response root.
     * Validates array presence and structure before iterating.
     *
     * @param usersNode the JSON node representing the users array
     * @param guildId the guild context (may be {@code null})
     * @param moderatorId the moderator's ID (must not be {@code null})
     * @return a list of parsed {@code ActionData} objects
     * @throws ActionDataParseException if usersNode is missing, null, or not an array
     * @throws NullPointerException if {@code moderatorId} is {@code null}
     */
    @NotNull
    private List<ActionData> parseUsers(
            @Nullable JsonNode usersNode,
            @NotNull GuildID guildId,
            @NotNull UserID moderatorId) {
        Objects.requireNonNull(moderatorId, "moderatorId must not be null");

        if (usersNode == null || !usersNode.isArray()) {
            throw new ActionDataParseException("Missing or invalid 'users' array in AI output");
        }

        List<ActionData> results = new ArrayList<>();
        for (JsonNode userNode : usersNode) {
            results.add(parseUser(userNode, guildId, moderatorId));
        }
        return results;
    }

    /**
     * Parses a single user object from the AI response.
     * Extracts user_id, action, reason, timeout_duration, ban_duration, and nested channel deletions.
     * Generates a random UUID for the action ID and builds the ActionData via ActionDataBuilder.
     *
     * @param userNode the JSON node representing a single user's moderation data
     * @param guildId the guild context (may be {@code null})
     * @param moderatorId the moderator's ID (must not be {@code null})
     * @return the constructed {@code ActionData}
     * @throws ActionDataParseException if required fields (user_id, action, reason) are missing or invalid
     * @throws NullPointerException if {@code userNode} or {@code moderatorId} is {@code null}
     */
    @NotNull
    private ActionData parseUser(
            @NotNull JsonNode userNode,
            @NotNull GuildID guildId,
            @NotNull UserID moderatorId) {
        Objects.requireNonNull(userNode, "userNode must not be null");
        Objects.requireNonNull(guildId, "guildId must not be null");
        Objects.requireNonNull(moderatorId, "moderatorId must not be null");

        UserID userId     = new UserID(requireText(userNode, "user_id"));
        ActionType action = parseActionType(requireText(userNode, "action"));
        String reason     = requireText(userNode, "reason");
        long timeoutDuration = userNode.path("timeout_duration").asLong(0);
        long banDuration     = userNode.path("ban_duration").asLong(0);

        UUID id = UUID.randomUUID();

        ActionDataBuilder builder = new ActionDataBuilder(
                id, Instant.now(), guildId, userId, moderatorId, action, reason, timeoutDuration, banDuration
        );

        JsonNode channelsNode = userNode.get("channels");
        if (channelsNode != null && channelsNode.isArray()) {
            for (JsonNode channelNode : channelsNode) {
                parseChannelDeletions(channelNode, builder);
            }
        }

        ActionData data = builder.build();
        logger.debug("Parsed ActionData: userId={}, action={}, deletions={}",
                userId, action, data.deletions().size());
        return data;
    }

    /**
     * Parses message deletion specifications from a channel object.
     * Extracts channel_id and message_ids_to_delete array, then adds each to the builder.
     *
     * @param channelNode the JSON node representing a channel with deletions
     * @param builder the ActionDataBuilder to accumulate deletions into (must not be {@code null})
     * @throws ActionDataParseException if channel_id is missing or invalid
     * @throws NullPointerException if {@code channelNode} or {@code builder} is {@code null}
     */
    private void parseChannelDeletions(
            @NotNull JsonNode channelNode,
            @NotNull ActionDataBuilder builder) {
        Objects.requireNonNull(channelNode, "channelNode must not be null");
        Objects.requireNonNull(builder, "builder must not be null");

        ChannelID channelId = new ChannelID(requireText(channelNode, "channel_id"));

        JsonNode messageIds = channelNode.get("message_ids_to_delete");
        if (messageIds == null || !messageIds.isArray()) return;

        for (JsonNode msgIdNode : messageIds) {
            MessageID messageId = new MessageID(msgIdNode.asText());
            builder.addMessageDeletion(new MessageDeletion(channelId, messageId));
        }
    }

    /**
     * Converts a raw action type string from the AI to the corresponding {@code ActionType} enum.
     * Case-insensitive lookup. Supported values: null, delete, warn, timeout, kick, ban.
     *
     * @param raw the action type string from the AI (case-insensitive)
     * @return the matched {@code ActionType}
     * @throws ActionDataParseException if the action type is not recognized
     * @throws NullPointerException if {@code raw} is {@code null}
     */
    @NotNull
    private ActionType parseActionType(@NotNull String raw) {
        Objects.requireNonNull(raw, "raw must not be null");

        ActionType type = ACTION_TYPE_MAP.get(raw.toLowerCase());
        if (type == null) {
            throw new ActionDataParseException("Unknown action type: '" + raw + "'");
        }
        return type;
    }

    /**
     * Extracts a required text field from a JSON node.
     * Throws an exception if the field is absent, null, or blank.
     *
     * @param node the JSON node to extract from (must not be {@code null})
     * @param field the field name (must not be {@code null})
     * @return the non-blank text value
     * @throws ActionDataParseException if the field is missing, null, or blank
     * @throws NullPointerException if {@code node} or {@code field} is {@code null}
     */
    @NotNull
    private String requireText(@NotNull JsonNode node, @NotNull String field) {
        Objects.requireNonNull(node, "node must not be null");
        Objects.requireNonNull(field, "field must not be null");

        JsonNode child = node.get(field);
        if (child == null || child.isNull() || child.asText().isBlank()) {
            throw new ActionDataParseException("Missing required field '" + field + "' in: " + node);
        }
        return child.asText();
    }

    /**
     * Exception thrown when ActionData JSON parsing fails.
     * Indicates malformed AI output, missing required fields, or invalid field values.
     */
    public static class ActionDataParseException extends RuntimeException {
        /**
         * Constructs a new exception with the given message.
         *
         * @param message descriptive error message
         */
        public ActionDataParseException(@NotNull String message) {
            super(Objects.requireNonNull(message, "message must not be null"));
        }

        /**
         * Constructs a new exception with message and cause.
         *
         * @param message descriptive error message
         * @param cause the underlying exception
         */
        public ActionDataParseException(@NotNull String message, @NotNull Throwable cause) {
            super(Objects.requireNonNull(message, "message must not be null"),
                    Objects.requireNonNull(cause, "cause must not be null"));
        }
    }
}