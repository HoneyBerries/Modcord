package net.honeyberries.ai;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.openai.models.chat.completions.*;
import net.honeyberries.datatypes.content.*;
import org.jetbrains.annotations.NotNull;

import java.util.ArrayList;
import java.util.List;

public class GuildModerationBatchToAIInput {

    private static final ObjectMapper objectMapper = new ObjectMapper();

    /**
     * Builds a user message with interleaved JSON context and labeled images.
     * The JSON references images by their UUID, and each image is then provided
     * inline after a text label so the model can correlate them.
     */
    public static ChatCompletionMessageParam createMessageFromGuildModerationBatch(
            @NotNull GuildModerationBatch guildModerationBatch)
            throws GuildModerationBatchSerializationException {

        try {
            // 1. Build the JSON payload (image_ids referenced inline per message)
            ObjectNode root = objectMapper.createObjectNode();

            ObjectNode guild = objectMapper.createObjectNode();
            guild.put("id", guildModerationBatch.guildId().toString());
            guild.put("name", guildModerationBatch.guildName());
            root.set("guild", guild);

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

            ArrayNode usersForModeration = objectMapper.createArrayNode();
            for (ModerationUser user : guildModerationBatch.users()) {
                usersForModeration.add(serializeModerationUser(user));
            }
            root.set("users_for_moderation", usersForModeration);

            ArrayNode userHistory = objectMapper.createArrayNode();
            for (ModerationUser user : guildModerationBatch.historyUsers()) {
                userHistory.add(serializeModerationUser(user));
            }
            root.set("user_history", userHistory);

            String jsonContent = objectMapper.writeValueAsString(root);

            // 2. Collect all images across all users and messages
            List<ModerationImage> allImages = collectAllImages(guildModerationBatch);

            // 3. Build the mixed content part list:
            //    [ JSON text ] + [ "Image <uuid>:", <image> ] for each image
            List<ChatCompletionContentPart> contentParts = new ArrayList<>();

            contentParts.add(textPart(
                "Below is the moderation batch data in JSON. Images attached to messages " +
                "are referenced by their image_id in the JSON. Each image is labeled " +
                "below using that same ID so you can correlate them.\n\n" + jsonContent
            ));

            if (!allImages.isEmpty()) {
                contentParts.add(textPart(
                    "The following images are referenced in the JSON above by their image_id:"
                ));

                for (ModerationImage image : allImages) {
                    // Label matches the image_id used in the JSON
                    contentParts.add(textPart("Image " + image.imageId() + ":"));
                    contentParts.add(imagePart(image.imageUrl().toString()));
                }
            }

            return ChatCompletionMessageParam.ofUser(
                ChatCompletionUserMessageParam.builder()
                    .content(ChatCompletionUserMessageParam.Content.ofArrayOfContentParts(contentParts))
                    .build()
            );

        } catch (JsonProcessingException e) {
            throw new GuildModerationBatchSerializationException(
                    "Failed to serialize GuildModerationBatch to JSON for guild: "
                            + guildModerationBatch.guildId(), e);
        } catch (Exception e) {
            throw new GuildModerationBatchSerializationException(
                    "Unexpected error while building AI input for guild: "
                            + guildModerationBatch.guildId(), e);
        }
    }

    // -------------------------------------------------------------------------
    // Helpers — content part builders
    // -------------------------------------------------------------------------

    private static ChatCompletionContentPart textPart(String text) {
        return ChatCompletionContentPart.ofText(
            ChatCompletionContentPartText.builder()
                .text(text)
                .build()
        );
    }

    private static ChatCompletionContentPart imagePart(String url) {
        return ChatCompletionContentPart.ofImageUrl(
            ChatCompletionContentPartImage.builder()
                .imageUrl(ChatCompletionContentPartImage.ImageUrl.builder()
                    .url(url)
                    .build())
                .build()
        );
    }

    // -------------------------------------------------------------------------
    // Helpers — image collection
    // -------------------------------------------------------------------------

    /**
     * Walks all users (moderation targets + history) and collects every
     * ModerationImage in message order, deduplicating by imageId.
     */
    private static List<ModerationImage> collectAllImages(GuildModerationBatch batch) {
        List<ModerationImage> images = new ArrayList<>();
        java.util.Set<java.util.UUID> seen = new java.util.LinkedHashSet<>();

        for (ModerationUser user : batch.users()) {
            collectImagesFromUser(user, images, seen);
        }
        for (ModerationUser user : batch.historyUsers()) {
            collectImagesFromUser(user, images, seen);
        }
        return images;
    }

    private static void collectImagesFromUser(
            ModerationUser user,
            List<ModerationImage> out,
            java.util.Set<java.util.UUID> seen) {
        for (ModerationUserChannel channel : user.channels()) {
            for (ModerationMessage message : channel.messages()) {
                for (ModerationImage image : message.images()) {
                    if (seen.add(image.imageId())) {
                        out.add(image);
                    }
                }
            }
        }
    }

    // -------------------------------------------------------------------------
    // JSON serialization
    // -------------------------------------------------------------------------

    private static ObjectNode serializeModerationUser(@NotNull ModerationUser user) {
        ObjectNode userNode = objectMapper.createObjectNode();
        userNode.put("user_id", user.userId().toString());
        userNode.put("username", user.username().username());
        userNode.put("join_date", user.joinDate().toString());

        ArrayNode rolesArray = objectMapper.createArrayNode();
        for (String role : user.roles()) {
            rolesArray.add(role);
        }
        userNode.set("roles", rolesArray);

        ArrayNode channelsArray = objectMapper.createArrayNode();
        for (ModerationUserChannel channel : user.channels()) {
            ObjectNode channelNode = objectMapper.createObjectNode();
            channelNode.put("channel_id", channel.channelId().toString());
            channelNode.put("channel_name", channel.channelName());

            ArrayNode messagesArray = objectMapper.createArrayNode();
            for (ModerationMessage message : channel.messages()) {
                ObjectNode messageNode = objectMapper.createObjectNode();
                messageNode.put("message_id", message.messageId().toString());
                messageNode.put("timestamp", message.timestamp().toString());
                messageNode.put("content", message.content());

                // image_ids here match the labels added to the content parts below
                ArrayNode imageIdsArray = objectMapper.createArrayNode();
                for (ModerationImage image : message.images()) {
                    imageIdsArray.add(image.imageId().toString());
                }
                messageNode.set("image_ids", imageIdsArray);

                messagesArray.add(messageNode);
            }
            channelNode.set("messages", messagesArray);
            channelsArray.add(channelNode);
        }
        userNode.set("channels", channelsArray);

        return userNode;
    }

    // -------------------------------------------------------------------------
    // Exception
    // -------------------------------------------------------------------------

    public static class GuildModerationBatchSerializationException extends Exception {
        public GuildModerationBatchSerializationException(String message) {
            super(message);
        }
        public GuildModerationBatchSerializationException(String message, Throwable cause) {
            super(message, cause);
        }
    }
}