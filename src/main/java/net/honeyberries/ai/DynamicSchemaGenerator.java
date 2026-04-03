package net.honeyberries.ai;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.openai.core.JsonValue;
import com.openai.models.ResponseFormatJsonSchema;
import net.honeyberries.datatypes.content.GuildModerationBatch;
import net.honeyberries.datatypes.content.ModerationUser;
import net.honeyberries.datatypes.content.ModerationUserChannel;
import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.MessageID;
import net.honeyberries.datatypes.discord.UserID;
import org.jetbrains.annotations.NotNull;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.*;

/**
 * Generates dynamic JSON schemas for AI inference based on guild moderation batch content.
 * Creates OpenAI-compatible schemas that constrain the AI's output to valid moderation actions and message deletions.
 * Supports variable numbers of users, channels, and messages, generating fixed-size arrays with proper constraints.
 * Uses a singleton pattern and provides exception handling for schema generation failures.
 */
public class DynamicSchemaGenerator {

    /** Logger for schema generation and error details. */
    private static final Logger logger = LoggerFactory.getLogger(DynamicSchemaGenerator.class);
    /** Singleton instance. */
    private static final DynamicSchemaGenerator INSTANCE = new DynamicSchemaGenerator();
    /** JSON object mapper for creating schema nodes. */
    private static final ObjectMapper mapper = new ObjectMapper();

    private DynamicSchemaGenerator() {}

    /**
     * Retrieves the singleton instance of the schema generator.
     *
     * @return the singleton {@code DynamicSchemaGenerator}
     */
    @NotNull
    public static DynamicSchemaGenerator getInstance() {
        return INSTANCE;
    }

    /**
     * Creates a simple type node with the given type name.
     * Example: {@code {"type": "string"}}
     *
     * @param typeName the JSON schema type (e.g., "string", "integer", "array", "object")
     * @return an object node with the type property set
     */
    @NotNull
    private static ObjectNode typeNode(@NotNull String typeName) {
        Objects.requireNonNull(typeName, "typeName must not be null");
        return mapper.createObjectNode().put("type", typeName);
    }

    /**
     * Creates an enumeration node that restricts a string to exactly one value.
     * Example: {@code {"type": "string", "enum": ["ban"]}}
     *
     * @param value the only allowed value for this enum
     * @return an object node with type and enum constraint
     */
    @NotNull
    private static ObjectNode stringEnum(@NotNull String value) {
        Objects.requireNonNull(value, "value must not be null");
        ObjectNode node = typeNode("string");
        node.putArray("enum").add(value);
        return node;
    }

    /**
     * Creates an integer range constraint node.
     * Example: {@code {"type": "integer", "minimum": 0, "maximum": 28 days in seconds}}
     *
     * @param min the inclusive minimum value
     * @param max the inclusive maximum value
     * @return an object node with type and range constraints
     */
    @NotNull
    private static ObjectNode intRange(int min, int max) {
        return typeNode("integer").put("minimum", min).put("maximum", max);
    }

    /**
     * Adds required fields list and disallows additional properties to an object schema.
     * This "seals" the object to match the exact structure expected by the caller.
     *
     * @param node the object schema node to seal
     * @param requiredFields the field names that must be present
     * @return the same node (for method chaining)
     */
    @NotNull
    private static ObjectNode seal(@NotNull ObjectNode node, @NotNull String... requiredFields) {
        Objects.requireNonNull(node, "node must not be null");
        Objects.requireNonNull(requiredFields, "requiredFields must not be null");
        ArrayNode req = node.putArray("required");
        for (String f : requiredFields) req.add(f);
        node.put("additionalProperties", false);
        return node;
    }

    /**
     * Creates an array schema with fixed size determined by the number of item schemas.
     * All items must match one of the provided schemas via oneOf constraint.
     * If schemas is empty, creates a zero-length array schema.
     *
     * @param schemas array node containing oneOf schemas
     * @return an object node representing a fixed-size array
     */
    @NotNull
    private static ObjectNode fixedArray(@NotNull ArrayNode schemas) {
        Objects.requireNonNull(schemas, "schemas must not be null");
        ObjectNode node = typeNode("array");
        if (!schemas.isEmpty()) {
            node.putObject("items").set("oneOf", schemas);
            node.put("minItems", schemas.size());
            node.put("maxItems", schemas.size());
        } else {
            node.put("maxItems", 0);
        }
        return node;
    }

    /**
     * Generates a complete JSON schema for the given moderation batch.
     * The schema constrains the AI's output to valid action types, message deletions, and duration ranges.
     * Handles empty batches gracefully by generating a schema that accepts zero users.
     *
     * @param batch the guild moderation batch containing users and context
     * @return an OpenAI-compatible response format schema
     * @throws DynamicSchemaGeneratorParseException if the batch has invalid or missing data
     * @throws NullPointerException if {@code batch} is {@code null}
     */
    @NotNull
    public ResponseFormatJsonSchema createDynamicOutputSchema(@NotNull GuildModerationBatch batch)
            throws DynamicSchemaGeneratorParseException {
        Objects.requireNonNull(batch, "batch must not be null");

        ObjectNode schemaNode = buildSchema(batch);

        Map<String, Object> schemaMap;

        schemaMap = mapper.convertValue(schemaNode, new TypeReference<>() {});

        ResponseFormatJsonSchema.JsonSchema jsonSchema =
                ResponseFormatJsonSchema.JsonSchema.builder()
                        .name("moderation_output")
                        .strict(true)
                        .putAdditionalProperty("schema", JsonValue.from(schemaMap))
                        .build();

        return ResponseFormatJsonSchema.builder()
                .jsonSchema(jsonSchema)
                .build();
    }

    /**
     * Builds the root JSON schema object from a moderation batch.
     * Separates current moderation targets from historical context users.
     * Excludes historical messages from the list of deletable message IDs.
     *
     * @param batch the moderation batch
     * @return the root schema object node
     * @throws DynamicSchemaGeneratorParseException if batch validation fails
     */
    @NotNull
    private ObjectNode buildSchema(@NotNull GuildModerationBatch batch)
            throws DynamicSchemaGeneratorParseException {
        Objects.requireNonNull(batch, "batch must not be null");

        String guildId = batch.guildId().toString();
        if (guildId.isBlank()) {
            throw new DynamicSchemaGeneratorParseException(
                    "Batch has a blank guildId — cannot build schema");
        }

        if (batch.isEmpty()) {
            logger.warn("Empty batch.users — no users to moderate");
            return buildEmptyBatchSchema(guildId);
        }

        Map<UserID, Map<ChannelID, Set<MessageID>>> userChannelMessages = new LinkedHashMap<>();

        for (ModerationUser user : batch.users()) {
            Map<ChannelID, Set<MessageID>> chMap = new LinkedHashMap<>();
            for (ModerationUserChannel uch : user.channels()) {
                Set<MessageID> msgIds = new HashSet<>();
                uch.messages().stream()
                        .filter(msg -> !msg.isHistoryContextWindow())
                        .forEach(msg -> msgIds.add(msg.messageId()));
                chMap.put(uch.channelId(), msgIds);
            }
            userChannelMessages.put(user.userId(), chMap);
        }

        for (ModerationUser historyUser : batch.historyUsers()) {
            if (!userChannelMessages.containsKey(historyUser.userId())) continue;

            Map<ChannelID, Set<MessageID>> chMap = userChannelMessages.get(historyUser.userId());
            for (ModerationUserChannel uch : historyUser.channels()) {
                chMap.computeIfAbsent(uch.channelId(), k -> new HashSet<>());
            }
        }

        ArrayNode userSchemas = buildUserSchemas(userChannelMessages);
        return buildRootSchema(guildId, userSchemas);
    }

    /**
     * Builds a schema for an empty moderation batch (no users to evaluate).
     *
     * @param guildId the guild ID as a string
     * @return a schema accepting a guild_id and empty users array
     */
    @NotNull
    private ObjectNode buildEmptyBatchSchema(@NotNull String guildId) {
        Objects.requireNonNull(guildId, "guildId must not be null");
        ObjectNode root = typeNode("object");
        ObjectNode props = root.putObject("properties");
        props.set("guild_id", stringEnum(guildId));
        props.putObject("users").put("type", "array").put("maxItems", 0);
        return seal(root, "guild_id", "users");
    }

    /**
     * Builds schemas for each user in the batch.
     * Each user schema includes action type, reason, channel deletions, and timeout/ban durations.
     *
     * @param userChannelMessages map from user ID to channels to message IDs
     * @return array node containing one schema per user
     */
    @NotNull
    private ArrayNode buildUserSchemas(@NotNull Map<UserID, Map<ChannelID, Set<MessageID>>> userChannelMessages) {
        Objects.requireNonNull(userChannelMessages, "userChannelMessages must not be null");
        ArrayNode userSchemas = mapper.createArrayNode();

        for (Map.Entry<UserID, Map<ChannelID, Set<MessageID>>> userEntry : userChannelMessages.entrySet()) {
            UserID userId = userEntry.getKey();
            Map<ChannelID, Set<MessageID>> chMap = userEntry.getValue();

            ArrayNode channelSchemas = buildChannelSchemas(chMap);

            ObjectNode userSchema = typeNode("object");
            ObjectNode userProps = userSchema.putObject("properties");

            userProps.set("user_id", stringEnum(userId.toString()));
            userProps.set("action", buildActionEnum());
            userProps.set("reason", typeNode("string"));
            userProps.set("channels", fixedArray(channelSchemas));
            userProps.set("timeout_duration", intRange(0, 28 * 24 * 60 * 60));
            userProps.set("ban_duration", intRange(-1, 365 * 24 * 60 * 60));

            seal(userSchema, "user_id", "action", "reason", "channels", "timeout_duration", "ban_duration");
            userSchemas.add(userSchema);
        }

        return userSchemas;
    }

    /**
     * Builds schemas for each channel in a user's context.
     * Each channel schema lists the message IDs available for deletion.
     *
     * @param chMap map from channel ID to set of deletable message IDs
     * @return array node containing one schema per channel
     */
    @NotNull
    private ArrayNode buildChannelSchemas(@NotNull Map<ChannelID, Set<MessageID>> chMap) {
        Objects.requireNonNull(chMap, "chMap must not be null");
        ArrayNode channelSchemas = mapper.createArrayNode();

        for (Map.Entry<ChannelID, Set<MessageID>> chEntry : chMap.entrySet()) {
            ChannelID channelId = chEntry.getKey();
            List<String> sortedMessageIds = chEntry.getValue().stream()
                    .map(MessageID::toString)
                    .sorted()
                    .toList();

            ObjectNode midConstraint = typeNode("array");
            if (!sortedMessageIds.isEmpty()) {
                ObjectNode items = midConstraint.putObject("items").put("type", "string");
                ArrayNode enumArr = items.putArray("enum");
                sortedMessageIds.forEach(enumArr::add);
            } else {
                midConstraint.putObject("items").put("type", "string");
                midConstraint.put("maxItems", 0);
            }

            ObjectNode channelSchema = typeNode("object");
            ObjectNode chProps = channelSchema.putObject("properties");
            chProps.set("channel_id", stringEnum(channelId.toString()));
            chProps.set("message_ids_to_delete", midConstraint);
            seal(channelSchema, "channel_id", "message_ids_to_delete");

            channelSchemas.add(channelSchema);
        }

        return channelSchemas;
    }

    /**
     * Builds the action type enumeration constraint.
     * Restricts the AI to valid moderation actions: null, delete, warn, timeout, kick, ban.
     *
     * @return an object node with string type and enum constraint
     */
    @NotNull
    private ObjectNode buildActionEnum() {
        ObjectNode actionProp = typeNode("string");
        ArrayNode actionEnum = actionProp.putArray("enum");
        List.of("null", "delete", "warn", "timeout", "kick", "ban").forEach(actionEnum::add);
        return actionProp;
    }

    /**
     * Builds the root schema object combining guild_id and users array.
     *
     * @param guildId the guild ID as a string
     * @param userSchemas array node of user schemas (one per user to evaluate)
     * @return the root object node
     */
    @NotNull
    private ObjectNode buildRootSchema(@NotNull String guildId, @NotNull ArrayNode userSchemas) {
        Objects.requireNonNull(guildId, "guildId must not be null");
        Objects.requireNonNull(userSchemas, "userSchemas must not be null");
        ObjectNode root = typeNode("object");
        ObjectNode rootProps = root.putObject("properties");
        rootProps.set("guild_id", stringEnum(guildId));
        rootProps.set("users", fixedArray(userSchemas));
        return seal(root, "guild_id", "users");
    }

    /**
     * Exception thrown when schema generation fails due to invalid batch data.
     */
    public static class DynamicSchemaGeneratorParseException extends RuntimeException {
        /**
         * Constructs a new exception with the given message.
         *
         * @param message descriptive error message
         */
        public DynamicSchemaGeneratorParseException(@NotNull String message) {
            super(Objects.requireNonNull(message, "message must not be null"));
        }

        /**
         * Constructs a new exception with message and cause.
         *
         * @param message descriptive error message
         * @param cause the underlying exception
         */
        public DynamicSchemaGeneratorParseException(@NotNull String message, @NotNull Throwable cause) {
            super(Objects.requireNonNull(message, "message must not be null"),
                    Objects.requireNonNull(cause, "cause must not be null"));
        }
    }
}