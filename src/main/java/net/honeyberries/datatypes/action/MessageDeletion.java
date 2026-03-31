package net.honeyberries.datatypes.action;

import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.MessageID;
import org.jetbrains.annotations.NotNull;

import java.util.Objects;

/**
 * Pairing of a channel and specific message to remove as part of a moderation action.
 * Keeps deletion coordinates explicit so callers can batch or log deletions accurately.
 */
public record MessageDeletion(
    @NotNull ChannelID channelId,
    @NotNull MessageID messageId
) {
    /**
     * Compact constructor ensuring both identifiers are provided.
     *
     * @param channelId channel containing the message to delete; must not be {@code null}
     * @param messageId message to remove; must not be {@code null}
     * @throws NullPointerException if any argument is {@code null}
     */
    public MessageDeletion {
        Objects.requireNonNull(channelId, "channelId must not be null");
        Objects.requireNonNull(messageId, "messageId must not be null");
    }
}
