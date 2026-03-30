package net.honeyberries.ai;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import net.honeyberries.datatypes.action.ActionData;
import net.honeyberries.datatypes.action.ActionDataBuilder;
import net.honeyberries.datatypes.action.ActionType;
import net.honeyberries.datatypes.action.MessageDeletion;
import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.discord.MessageID;
import net.honeyberries.datatypes.discord.UserID;
import org.jetbrains.annotations.NotNull;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;

public class ActionDataJSONParser {

    private static final Logger logger = LoggerFactory.getLogger(ActionDataJSONParser.class);
    private static final ObjectMapper mapper = new ObjectMapper();

    /**
     * Maps the AI's lowercase action strings to ActionType enum values.
     * "null" -> ActionType.NULL, "ban" -> ActionType.BAN, etc.
     */
    private static final Map<String, ActionType> ACTION_TYPE_MAP = Map.of(
            "null",    ActionType.NULL,
            "delete",  ActionType.DELETE,
            "warn",    ActionType.WARN,
            "timeout", ActionType.TIMEOUT,
            "kick",    ActionType.KICK,
            "ban",     ActionType.BAN
    );

    /**
     * Parses the AI's JSON output into a list of ActionData.
     *
     * @param json The raw JSON string returned by the AI.
     * @return A list of ActionData, one per user in the batch.
     * @throws ActionDataParseException if the JSON is malformed or missing required fields.
     */
    @NotNull
    public List<ActionData> parse(@NotNull String json, GuildID guildId) {
        try {
            JsonNode root = mapper.readTree(json);
            return parseUsers(root.get("users"), guildId);
        } catch (ActionDataParseException e) {
            throw e;
        } catch (Exception e) {
            throw new ActionDataParseException("Failed to parse AI JSON output", e);
        }
    }

    private List<ActionData> parseUsers(JsonNode usersNode, GuildID guildId) {
        if (usersNode == null || !usersNode.isArray()) {
            throw new ActionDataParseException("Missing or invalid 'users' array in AI output");
        }

        List<ActionData> results = new ArrayList<>();
        for (JsonNode userNode : usersNode) {
            results.add(parseUser(userNode, guildId));
        }
        return results;
    }

    private ActionData parseUser(JsonNode userNode, GuildID guildId) {
        UserID userId     = new UserID(requireText(userNode, "user_id"));
        ActionType action = parseActionType(requireText(userNode, "action"));
        String reason     = requireText(userNode, "reason");
        long timeoutDuration = userNode.path("timeout_duration").asLong(0);
        long banDuration     = userNode.path("ban_duration").asLong(0);

        UUID id = UUID.randomUUID();

        ActionDataBuilder builder = new ActionDataBuilder(
                id, guildId, userId, action, reason, timeoutDuration, banDuration
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

    private void parseChannelDeletions(JsonNode channelNode, ActionDataBuilder builder) {
        ChannelID channelId = new ChannelID(requireText(channelNode, "channel_id"));

        JsonNode messageIds = channelNode.get("message_ids_to_delete");
        if (messageIds == null || !messageIds.isArray()) return;

        for (JsonNode msgIdNode : messageIds) {
            MessageID messageId = new MessageID(msgIdNode.asText());
            builder.addMessageDeletion(new MessageDeletion(channelId, messageId));
        }
    }

    private ActionType parseActionType(String raw) {
        ActionType type = ACTION_TYPE_MAP.get(raw.toLowerCase());
        if (type == null) {
            throw new ActionDataParseException("Unknown action type: '" + raw + "'");
        }
        return type;
    }

    /** Gets a required text field from a JSON node, throwing if absent or blank. */
    private String requireText(JsonNode node, String field) {
        JsonNode child = node.get(field);
        if (child == null || child.isNull() || child.asText().isBlank()) {
            throw new ActionDataParseException("Missing required field '" + field + "' in: " + node);
        }
        return child.asText();
    }

    // -------------------------------------------------------------------------
    // Exception
    // -------------------------------------------------------------------------

    public static class ActionDataParseException extends RuntimeException {
        public ActionDataParseException(String message) {
            super(message);
        }
        public ActionDataParseException(String message, Throwable cause) {
            super(message, cause);
        }
    }
}