package net.honeyberries.datatypes.content;

import net.dv8tion.jda.api.entities.Message;
import org.jetbrains.annotations.NotNull;

import java.net.MalformedURLException;
import java.net.URI;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.Objects;
import java.util.UUID;

/**
 * Immutable wrapper for a moderation image with its ID and URL.
 * Encapsulates attachment details so that downstream components can treat images uniformly regardless of the original Discord payload.
 */
public record ModerationImage(
        @NotNull UUID imageId,
        @NotNull URL imageUrl
) {

    /**
     * Creates a moderation image from a JDA attachment, deriving a stable UUID from the attachment id.
     *
     * @param attachment Discord attachment to normalize; must not be {@code null}
     * @throws NullPointerException     if {@code attachment} is {@code null}
     * @throws IllegalArgumentException if the attachment URL is malformed
     */
    public ModerationImage(@NotNull Message.Attachment attachment) {
        this(
                UUID.nameUUIDFromBytes(Objects.requireNonNull(attachment, "attachment must not be null").getId().getBytes(StandardCharsets.UTF_8)),
                toUrl(attachment.getUrl())
        );
    }

    private static URL toUrl(@NotNull String url) {
        Objects.requireNonNull(url, "url must not be null");
        try {
            return URI.create(url).toURL();
        } catch (MalformedURLException e) {
            throw new IllegalArgumentException("Invalid URL for attachment: " + url, e);
        }
    }
}
