package net.honeyberries.ai;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.openai.models.chat.completions.ChatCompletionMessageParam;
import com.openai.models.chat.completions.ChatCompletionUserMessageParam;
import net.honeyberries.datatypes.content.ChannelContext;
import net.honeyberries.datatypes.content.GuildModerationBatch;
import net.honeyberries.datatypes.content.ModerationMessage;
import net.honeyberries.datatypes.content.ModerationUser;
import net.honeyberries.datatypes.content.ModerationUserChannel;

public class GuildModerationBatchToAIInput {

    private static final ObjectMapper objectMapper = new ObjectMapper();

    public static ChatCompletionMessageParam createMessageFromGuildModerationBatch(GuildModerationBatch guildModerationBatch) {
        ObjectNode root = objectMapper.createObjectNode();

        // Guild section
        ObjectNode guild = objectMapper.createObjectNode();
        guild.put("id", guildModerationBatch.guildId().toString());
        guild.put("name", guildModerationBatch.guildName());
        root.set("guild", guild);

        // Context section with channels
        ObjectNode context = objectMapper.createObjectNode();
        ArrayNode channels = objectMapper.createArrayNode();
        for (ChannelContext channel : guildModerationBatch.channels().values()) {
            ObjectNode channelNode = objectMapper.createObjectNode();
            channelNode.put("id", channel.channelId().toString());
            channelNode.put("name", channel.channelName());
            channelNode.put("guidelines", channel.guidelines());
            channelNode.put("message_count", channel.messageCount());
            channels.add(channelNode);
        }
        context.set("channels", channels);
        root.set("context", context);

        // Users for moderation
        ArrayNode usersForModeration = objectMapper.createArrayNode();
        for (ModerationUser user : guildModerationBatch.users()) {
            usersForModeration.add(serializeModerationUser(user));
        }
        root.set("users_for_moderation", usersForModeration);

        // User history
        ArrayNode userHistory = objectMapper.createArrayNode();
        for (ModerationUser user : guildModerationBatch.historyUsers()) {
            userHistory.add(serializeModerationUser(user));
        }
        root.set("user_history", userHistory);

        // Convert to JSON string
        String jsonContent = root.toString();

        // Return as ChatCompletionUserMessageParam
        return ChatCompletionMessageParam.ofUser(
            ChatCompletionUserMessageParam.builder()
                .content(jsonContent)
                .build()
        );
    }

    private static ObjectNode serializeModerationUser(ModerationUser user) {
        ObjectNode userNode = objectMapper.createObjectNode();
        userNode.put("user_id", user.userId().toString());
        userNode.put("username", user.username().username());
        userNode.put("join_date", user.joinDate().toString());

        // Roles array
        ArrayNode rolesArray = objectMapper.createArrayNode();
        for (String role : user.roles()) {
            rolesArray.add(role);
        }
        userNode.set("roles", rolesArray);

        // Channels array
        ArrayNode channelsArray = objectMapper.createArrayNode();
        for (ModerationUserChannel channel : user.channels()) {
            ObjectNode channelNode = objectMapper.createObjectNode();
            channelNode.put("channel_id", channel.channelId().toString());
            channelNode.put("channel_name", channel.channelName());

            // Messages array
            ArrayNode messagesArray = objectMapper.createArrayNode();
            for (ModerationMessage message : channel.messages()) {
                ObjectNode messageNode = objectMapper.createObjectNode();
                messageNode.put("message_id", message.messageId().toString());
                messageNode.put("timestamp", message.timestamp().toString());
                messageNode.put("content", message.content());
                messagesArray.add(messageNode);
            }
            channelNode.set("messages", messagesArray);
            channelsArray.add(channelNode);
        }
        userNode.set("channels", channelsArray);

        return userNode;
    }

}
