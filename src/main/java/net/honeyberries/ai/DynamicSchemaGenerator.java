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

public class DynamicSchemaGenerator {

    private static final Logger logger = LoggerFactory.getLogger(DynamicSchemaGenerator.class);
    private static final DynamicSchemaGenerator INSTANCE = new DynamicSchemaGenerator();
    private static final ObjectMapper mapper = new ObjectMapper();

    private DynamicSchemaGenerator() {}

    public static DynamicSchemaGenerator getInstance() {
        return INSTANCE;
    }

    // -------------------------------------------------------------------------
    // Helpers
    // -------------------------------------------------------------------------

    /** {"type": typeName} */
    private static ObjectNode typeNode(String typeName) {
        return mapper.createObjectNode().put("type", typeName);
    }

    /** {"type": "string", "enum": [value]} */
    private static ObjectNode stringEnum(String value) {
        ObjectNode node = typeNode("string");
        node.putArray("enum").add(value);
        return node;
    }

    /** {"type": "integer", "minimum": min, "maximum": max} */
    private static ObjectNode intRange(int min, int max) {
        return typeNode("integer").put("minimum", min).put("maximum", max);
    }

    /**
     * Seals an object by adding "required" and "additionalProperties: false".
     * Returns the same node for chaining.
     */
    private static ObjectNode seal(ObjectNode node, String... requiredFields) {
        ArrayNode req = node.putArray("required");
        for (String f : requiredFields) req.add(f);
        node.put("additionalProperties", false);
        return node;
    }

    /**
     * Builds a fixed-size array schema from a set of oneOf schemas.
     * If schemas is empty, returns {"type": "array", "maxItems": 0}.
     */
    private static ObjectNode fixedArray(ArrayNode schemas) {
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

    // -------------------------------------------------------------------------
    // Public API
    // -------------------------------------------------------------------------

    @NotNull
    public ResponseFormatJsonSchema createDynamicOutputSchema(GuildModerationBatch batch) {
        ObjectNode schemaNode = buildSchema(batch);
        Map<String, Object> schemaMap = mapper.convertValue(schemaNode, new TypeReference<>() {});

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

    // -------------------------------------------------------------------------
    // Schema builder
    // -------------------------------------------------------------------------

    @NotNull
    private ObjectNode buildSchema(GuildModerationBatch batch) {
        String guildId = batch.guildId().toString();

        if (batch.isEmpty()) {
            logger.warn("Empty batch.users — no users to moderate");
            return buildEmptyBatchSchema(guildId);
        }

        // user -> channel -> non-history message IDs only
        Map<UserID, Map<ChannelID, Set<MessageID>>> userChannelMessages = new LinkedHashMap<>();

        for (ModerationUser user : batch.users()) {
            Map<ChannelID, Set<MessageID>> chMap = new LinkedHashMap<>();
            for (ModerationUserChannel uch : user.channels()) {
                Set<MessageID> msgIds = new HashSet<>();
                uch.messages().stream()
                        .filter(msg -> !msg.isHistoryContextWindow())  // exclude history from deletable IDs
                        .forEach(msg -> msgIds.add(msg.messageId()));
                chMap.put(uch.channelId(), msgIds);
            }
            userChannelMessages.put(user.userId(), chMap);
        }

        // Merge history users' channels in (without adding their message IDs)
        for (ModerationUser historyUser : batch.historyUsers()) {
            if (!userChannelMessages.containsKey(historyUser.userId())) continue;

            Map<ChannelID, Set<MessageID>> chMap = userChannelMessages.get(historyUser.userId());
            for (ModerationUserChannel uch : historyUser.channels()) {
                // Only register the channel — history messages are never deletable
                chMap.computeIfAbsent(uch.channelId(), k -> new HashSet<>());
            }
        }

        ArrayNode userSchemas = buildUserSchemas(userChannelMessages);
        return buildRootSchema(guildId, userSchemas);
    }

    private ObjectNode buildEmptyBatchSchema(String guildId) {
        ObjectNode root = typeNode("object");
        ObjectNode props = root.putObject("properties");
        props.set("guild_id", stringEnum(guildId));
        props.putObject("users").put("type", "array").put("maxItems", 0);
        return seal(root, "guild_id", "users");
    }

    private ArrayNode buildUserSchemas(Map<UserID, Map<ChannelID, Set<MessageID>>> userChannelMessages) {
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

    private ArrayNode buildChannelSchemas(Map<ChannelID, Set<MessageID>> chMap) {
        ArrayNode channelSchemas = mapper.createArrayNode();

        for (Map.Entry<ChannelID, Set<MessageID>> chEntry : chMap.entrySet()) {
            ChannelID channelId = chEntry.getKey();
            List<String> sortedMids = chEntry.getValue().stream()
                    .map(MessageID::toString)
                    .sorted()
                    .toList();

            ObjectNode midConstraint = typeNode("array");
            if (!sortedMids.isEmpty()) {
                ObjectNode items = midConstraint.putObject("items").put("type", "string");
                ArrayNode enumArr = items.putArray("enum");
                sortedMids.forEach(enumArr::add);
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

    private ObjectNode buildActionEnum() {
        ObjectNode actionProp = typeNode("string");
        ArrayNode actionEnum = actionProp.putArray("enum");
        List.of("null", "delete", "warn", "timeout", "kick", "ban").forEach(actionEnum::add);
        return actionProp;
    }

    private ObjectNode buildRootSchema(String guildId, ArrayNode userSchemas) {
        ObjectNode root = typeNode("object");
        ObjectNode rootProps = root.putObject("properties");
        rootProps.set("guild_id", stringEnum(guildId));
        rootProps.set("users", fixedArray(userSchemas));
        return seal(root, "guild_id", "users");
    }
}