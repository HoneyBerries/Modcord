package net.honeyberries.datatypes.content;

import net.dv8tion.jda.api.entities.Message;
import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.discord.MessageID;
import net.honeyberries.datatypes.discord.UserID;
import net.honeyberries.message.EmbedParser;
import org.jetbrains.annotations.NotNull;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

/**
 * Normalized representation of a Discord message used for moderation decisions.
 * Captures message metadata, author, channel context, and any attached images so the AI pipeline receives consistent inputs.
 * Instances can represent live messages or historical context depending on the {@code isHistoryContextWindow} flag.
 */
public record ModerationMessage(
        @NotNull MessageID messageId,
        @NotNull UserID userId,
        @NotNull String content,
        @NotNull LocalDateTime timestamp,
        @NotNull GuildID guildId,
        @NotNull ChannelID channelId,
        @NotNull List<ModerationImage> images,
        boolean isHistoryContextWindow
) {
    /**
     * Validates non-null fields and preserves immutability of the images list reference.
     *
     * @param messageId              identifier of the Discord message; must not be {@code null}
     * @param userId                 identifier of the author; must not be {@code null}
     * @param content                message content or parsed embed text; must not be {@code null}
     * @param timestamp              message creation time; must not be {@code null}
     * @param guildId                guild containing the message; must not be {@code null}
     * @param channelId              channel containing the message; must not be {@code null}
     * @param images                 attachments treated as moderation-relevant images; may be empty but not {@code null}
     * @param isHistoryContextWindow indicates whether the message came from a historical fetch window
     * @throws NullPointerException if any non-nullable argument is {@code null}
     */
    public ModerationMessage {
        Objects.requireNonNull(messageId, "messageId must not be null");
        Objects.requireNonNull(userId, "userId must not be null");
        Objects.requireNonNull(content, "content must not be null");
        Objects.requireNonNull(timestamp, "timestamp must not be null");
        Objects.requireNonNull(guildId, "guildId must not be null");
        Objects.requireNonNull(channelId, "channelId must not be null");
        Objects.requireNonNull(images, "images must not be null");
    }

    /**
     * Convenience constructor without images and history flag.
     *
     * @param messageId identifier of the Discord message; must not be {@code null}
     * @param userId    identifier of the author; must not be {@code null}
     * @param content   message content or parsed embed text; must not be {@code null}
     * @param timestamp message creation time; must not be {@code null}
     * @param guildId   guild containing the message; must not be {@code null}
     * @param channelId channel containing the message; must not be {@code null}
     * @throws NullPointerException if any required argument is {@code null}
     */
    public ModerationMessage(
            @NotNull MessageID messageId,
            @NotNull UserID userId,
            @NotNull String content,
            @NotNull LocalDateTime timestamp,
            @NotNull GuildID guildId,
            @NotNull ChannelID channelId
    ) {
        this(messageId, userId, content, timestamp, guildId, channelId, List.of(), false);
    }

    /**
     * Builds a {@link ModerationMessage} from a JDA {@link Message} payload.
     * Extracts text content (including embeds), attachments, and identifiers, marking whether the message came from history.
     *
     * @param msg                   JDA message to normalize; must not be {@code null}
     * @param isHistoryContextWindow {@code true} if the message was fetched as historical context
     * @return normalized moderation message with extracted attachments
     * @throws NullPointerException if {@code msg} is {@code null}
     */
    @NotNull
    public static ModerationMessage fromMessage(@NotNull Message msg, boolean isHistoryContextWindow) {
        Objects.requireNonNull(msg, "msg must not be null");

        if (msg.getEmbeds().isEmpty()) {
            MessageID msgId = MessageID.fromMessage(msg);
            GuildID guildID = GuildID.fromGuild(msg.getGuild());
            ChannelID channelID = ChannelID.fromChannel(msg.getChannel());
            UserID authorId = UserID.fromUser(msg.getAuthor());
            String content = msg.getContentDisplay();
            LocalDateTime timestamp = msg.getTimeCreated().toLocalDateTime();
            List<ModerationImage> images = new ArrayList<>();

            for (Message.Attachment attachment : msg.getAttachments()) {
                if (attachment.isImage()) {
                    images.add(new ModerationImage(attachment));
                }
            }

            return new ModerationMessage(msgId, authorId, content, timestamp, guildID, channelID, images, isHistoryContextWindow);

        } else {
            String content = EmbedParser.parseEmbed(msg);
            List<ModerationImage> images = new ArrayList<>();

            for (Message.Attachment attachment : msg.getAttachments()) {
                if (attachment.isImage()) {
                    images.add(new ModerationImage(attachment));
                }
            }

            return new ModerationMessage(
                    MessageID.fromMessage(msg),
                    UserID.fromUser(msg.getAuthor()),
                    content,
                    msg.getTimeCreated().toLocalDateTime(),
                    GuildID.fromGuild(msg.getGuild()),
                    ChannelID.fromChannel(msg.getChannel()),
                    images,
                    isHistoryContextWindow
            );
        }

    }

    /**
     * Returns a copy flagged as historical context while retaining all other fields.
     *
     * @return new {@link ModerationMessage} instance marked as history
     */
    @NotNull
    public ModerationMessage markAsHistory() {
        return new ModerationMessage(this.messageId(), this.userId(), this.content(), this.timestamp(), this.guildId(), this.channelId(), this.images(), true);
    }

    /**
     * Returns a new instance with the given images appended to the current list.
     *
     * @param images images to append; may be empty but must not be {@code null}
     * @return new {@link ModerationMessage} containing merged images
     * @throws NullPointerException if {@code images} is {@code null}
     */
    @NotNull
    public ModerationMessage addImages(@NotNull List<ModerationImage> images) {
        List<ModerationImage> mergedImages = new ArrayList<>(this.images());
        mergedImages.addAll(Objects.requireNonNull(images, "images must not be null"));

        return new ModerationMessage(
                this.messageId(),
                this.userId(),
                this.content(),
                this.timestamp(),
                this.guildId(),
                this.channelId(),
                mergedImages,
                this.isHistoryContextWindow()
        );
    }

    /**
     * Returns a new instance with a single image appended.
     *
     * @param image image to add; must not be {@code null}
     * @return new {@link ModerationMessage} containing the added image
     * @throws NullPointerException if {@code image} is {@code null}
     */
    @NotNull
    public ModerationMessage addImage(@NotNull ModerationImage image) {
        return addImages(List.of(Objects.requireNonNull(image, "image must not be null")));
    }

}
