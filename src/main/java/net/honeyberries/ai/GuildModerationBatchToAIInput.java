package net.honeyberries.ai;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.openai.models.chat.completions.*;
import net.honeyberries.datatypes.content.*;
import org.jetbrains.annotations.NotNull;

import java.util.*;

/**
 * Converts {@code GuildModerationBatch} data into AI-compatible input format with interleaved images.
 * Produces a mixed-content user message containing JSON context + image labels + image URLs.
 * Handles collection and deduplication of images across all users and messages, ensuring images are
 * accessible for correlation by the LLM.
 */
public class GuildModerationBatchToAIInput {

    /** JSON object mapper for serializing batch data. */
    private static final ObjectMapper objectMapper = new ObjectMapper();

    private GuildModerationBatchToAIInput() {}

    /**
     * Creates an AI-friendly chat message from a guild moderation batch.
     * Combines structured JSON data (guild, channels, users, messages) with image URLs,
     * each labeled by its UUID so the model can correlate JSON references to images.
     * <p>
     * JSON structure:
     * - guild: interactionID, name
     * - context: channels with guidelines and message counts
     * - users_for_moderation: current moderation targets with their full message history and images
     * - user_history: historical context users with their message history (for trend analysis)
     * <p>
     * Images are deduplicated by imageId across all users and messages, then appended as:
     * "Image {imageId}:" (text label) followed by the image URL.
     *
     * @param guildModerationBatch the batch containing guild, users, messages, and images to convert
     * @return a {@code ChatCompletionMessageParam} with mixed text/image content ready for AI inference
     * @throws GuildModerationBatchSerializationException if JSON serialization fails or batch data is invalid
     * @throws NullPointerException if {@code guildModerationBatch} is {@code null}
     */
    @NotNull
    public static ChatCompletionUserMessageParam createMessageFromGuildModerationBatch(
            @NotNull GuildModerationBatch guildModerationBatch)
            throws GuildModerationBatchSerializationException {
        Objects.requireNonNull(guildModerationBatch, "guildModerationBatch must not be null");

        try {
            // 1. Build the JSON payload (image_ids referenced inline per message)
            ObjectNode root = objectMapper.createObjectNode();

            ObjectNode guild = objectMapper.createObjectNode();
            guild.put("id", guildModerationBatch.guildId().toString());
            guild.put("name", guildModerationBatch.guildName());
            root.set("guild", guild);

            ObjectNode context = objectMapper.createObjectNode();
            ArrayNode channels = objectMapper.createArrayNode();
            for (ChannelMetadata channel : guildModerationBatch.channels().values()) {
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

            return ChatCompletionUserMessageParam.builder()
                    .content(ChatCompletionUserMessageParam.Content.ofArrayOfContentParts(contentParts))
                    .build();

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

    /**
     * Creates a text content part for inclusion in a mixed-content message.
     *
     * @param text the text content (must not be {@code null})
     * @return a text-based {@code ChatCompletionContentPart}
     * @throws NullPointerException if {@code text} is {@code null}
     */
    @NotNull
    private static ChatCompletionContentPart textPart(@NotNull String text) {
        Objects.requireNonNull(text, "text must not be null");
        return ChatCompletionContentPart.ofText(
            ChatCompletionContentPartText.builder()
                .text(text)
                .build()
        );
    }

    /**
     * Creates an image URL content part for inclusion in a mixed-content message.
     *
     * @param url the image URL as a string (must not be {@code null})
     * @return an image URL-based {@code ChatCompletionContentPart}
     * @throws NullPointerException if {@code url} is {@code null}
     */
    @NotNull
    private static ChatCompletionContentPart imagePart(@NotNull String url) {
        Objects.requireNonNull(url, "url must not be null");
        return ChatCompletionContentPart.ofImageUrl(
            ChatCompletionContentPartImage.builder()
                .imageUrl(ChatCompletionContentPartImage.ImageUrl.builder()
                    .url(url)
                    .build())
                .build()
        );
    }

    /**
     * Collects all images from moderation targets and history users.
     * Walks through all users, channels, and messages in document order,
     * deduplicates by imageId using a linked set to preserve order, and returns the list.
     *
     * @param batch the moderation batch to scan (must not be {@code null})
     * @return a deduplicator list of images in encounter order
     * @throws NullPointerException if {@code batch} is {@code null}
     */
    @NotNull
    private static List<ModerationImage> collectAllImages(@NotNull GuildModerationBatch batch) {
        Objects.requireNonNull(batch, "batch must not be null");
        List<ModerationImage> images = new ArrayList<>();
        Set<UUID> seen = new LinkedHashSet<>();

        for (ModerationUser user : batch.users()) {
            collectImagesFromUser(user, images, seen);
        }
        for (ModerationUser user : batch.historyUsers()) {
            collectImagesFromUser(user, images, seen);
        }
        return images;
    }

    /**
     * Collects images from all channels and messages of a single user.
     * Adds each image to the output list only once (first seen), updating the seen set.
     *
     * @param user the user to scan (must not be {@code null})
     * @param out the output list to append new images to (must not be {@code null})
     * @param seen the set of already-seen imageIds to prevent duplicates (must not be {@code null})
     * @throws NullPointerException if any parameter is {@code null}
     */
    private static void collectImagesFromUser(
            @NotNull ModerationUser user,
            @NotNull List<ModerationImage> out,
            @NotNull Set<UUID> seen) {
        Objects.requireNonNull(user, "user must not be null");
        Objects.requireNonNull(out, "out must not be null");
        Objects.requireNonNull(seen, "seen must not be null");

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

    /**
     * Serializes a moderation user to a JSON object node.
     * Includes user_id, username, join_date, roles, and nested channels with messages.
     * Each message includes message_id, timestamp, content, and image_ids array.
     * Note: image_ids are UUIDs that are matched to labels in the content parts.
     *
     * @param user the user to serialize (must not be {@code null})
     * @return a JSON object node representation of the user
     * @throws NullPointerException if {@code user} is {@code null}
     */
    @NotNull
    private static ObjectNode serializeModerationUser(@NotNull ModerationUser user) {
        Objects.requireNonNull(user, "user must not be null");

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

    /**
     * Exception thrown when guild moderation batch serialization to AI input format fails.
     * Indicates JSON processing errors or data structure issues.
     */
    public static class GuildModerationBatchSerializationException extends Exception {
        /**
         * Constructs a new exception with the given message.
         *
         * @param message descriptive error message
         */
        public GuildModerationBatchSerializationException(@NotNull String message) {
            super(Objects.requireNonNull(message, "message must not be null"));
        }

        /**
         * Constructs a new exception with message and cause.
         *
         * @param message descriptive error message
         * @param cause the underlying exception
         */
        public GuildModerationBatchSerializationException(@NotNull String message, @NotNull Throwable cause) {
            super(Objects.requireNonNull(message, "message must not be null"),
                    Objects.requireNonNull(cause, "cause must not be null"));
        }
    }
}