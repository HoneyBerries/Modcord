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

/**
 * A message belonging to a user in a channel that will be sent to the pipeline.
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
     * Convenience constructor without images and history flag.
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

    public static ModerationMessage fromMessage(Message msg, boolean isHistoryContextWindow) {

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

    public ModerationMessage markAsHistory() {
        return new ModerationMessage(this.messageId(), this.userId(), this.content(), this.timestamp(), this.guildId(), this.channelId(), this.images(), true);
    }


    public ModerationMessage addImages(List<ModerationImage> images) {
        List<ModerationImage> mergedImages = new ArrayList<>(this.images());
        mergedImages.addAll(images);

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

    public ModerationMessage addImage(ModerationImage image) {
        return addImages(List.of(image));
    }

}

