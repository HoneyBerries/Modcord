package net.honeyberries.datatypes.content;

import net.dv8tion.jda.api.entities.Message;
import org.jetbrains.annotations.NotNull;

import java.net.MalformedURLException;
import java.net.URI;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.UUID;

/**
 * Immutable wrapper for a moderation image with its ID and URL.
 */
public record ModerationImage(
        @NotNull UUID imageId,
        @NotNull URL imageUrl
) {

    public ModerationImage(Message.Attachment attachment) {
        this(
                UUID.nameUUIDFromBytes(attachment.getId().getBytes(StandardCharsets.UTF_8)),
                toUrl(attachment.getUrl())
        );
    }

    private static URL toUrl(String url) {
        try {
            return URI.create(url).toURL();
        } catch (MalformedURLException e) {
            throw new IllegalArgumentException("Invalid URL for attachment: " + url, e);
        }
    }
}
