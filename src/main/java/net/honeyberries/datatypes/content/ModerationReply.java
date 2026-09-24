package net.honeyberries.datatypes.content;

import net.dv8tion.jda.api.entities.Member;
import net.dv8tion.jda.api.entities.Message;
import net.dv8tion.jda.api.entities.MessageReference;
import net.dv8tion.jda.api.entities.MessageType;
import net.honeyberries.datatypes.discord.MessageID;
import net.honeyberries.datatypes.discord.UserID;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;

import java.util.Objects;

/**
 * Describes the message that a moderated message is replying to.
 * The replied-to message may be outside the fetched history window or deleted, so its author and content
 * are captured from Discord's reply payload when available and are {@code null} otherwise.
 */
public record ModerationReply(
        @NotNull MessageID messageId,
        @Nullable UserID authorId,
        @Nullable String authorName,
        @Nullable String content
) {
    /**
     * Compact constructor enforcing the required message reference.
     *
     * @param messageId  identifier of the replied-to message; must not be {@code null}
     * @param authorId   author of the replied-to message, or {@code null} if unavailable
     * @param authorName display name of that author, or {@code null} if unavailable
     * @param content    text of the replied-to message, or {@code null} if unavailable
     * @throws NullPointerException if {@code messageId} is {@code null}
     */
    public ModerationReply {
        Objects.requireNonNull(messageId, "messageId must not be null");
    }

    /**
     * Extracts reply information from a JDA message.
     * Only genuine inline replies count; forwards, pin notices, and other system references return {@code null}.
     *
     * @param msg the message to inspect; must not be {@code null}
     * @return the reply details, or {@code null} if the message is not a reply
     * @throws NullPointerException if {@code msg} is {@code null}
     */
    @Nullable
    public static ModerationReply fromMessage(@NotNull Message msg) {
        Objects.requireNonNull(msg, "msg must not be null");

        MessageReference reference = msg.getMessageReference();
        if (msg.getType() != MessageType.INLINE_REPLY
                || reference == null
                || reference.getType() != MessageReference.MessageReferenceType.DEFAULT) {
            return null;
        }

        MessageID messageId = new MessageID(reference.getMessageIdLong());
        Message referenced = msg.getReferencedMessage();
        if (referenced == null) {
            // Original was deleted or not included in the payload
            return new ModerationReply(messageId, null, null, null);
        }

        Member member = referenced.getMember();
        String authorName = member != null ? member.getEffectiveName() : referenced.getAuthor().getEffectiveName();
        return new ModerationReply(
                messageId,
                UserID.fromUser(referenced.getAuthor()),
                authorName,
                referenced.getContentDisplay()
        );
    }
}
