package net.honeyberries.message;

import net.dv8tion.jda.api.entities.Message;
import net.dv8tion.jda.api.entities.MessageEmbed;
import org.jetbrains.annotations.NotNull;

import java.util.Objects;

/**
 * Utility for flattening Discord embeds into readable plain text.
 * Provides a consistent representation so embed content can be fed into the moderation pipeline alongside message text.
 */
public final class EmbedParser {

    private EmbedParser() {
        // Utility class
    }

    /**
     * Extracts the human-readable contents of all embeds in a message.
     * Titles are bolded, fields are rendered as name/value pairs, and embeds are separated by a delimiter.
     *
     * @param message message containing zero or more embeds; must not be {@code null}
     * @return trimmed plain-text representation of the embeds, or an empty string when none are present
     * @throws NullPointerException if {@code message} is {@code null}
     */
    @NotNull
    public static String parseEmbed(@NotNull Message message) {
        Objects.requireNonNull(message, "message must not be null");
        StringBuilder sb = new StringBuilder();

        if (message.getEmbeds().isEmpty()) {
            return "";
        }

        for (MessageEmbed embed : message.getEmbeds()) {

            if (embed.getTitle() != null) {
                sb.append("**").append(embed.getTitle()).append("**\n");
            }

            if (embed.getDescription() != null) {
                sb.append(embed.getDescription()).append("\n");
            }

            if (embed.getAuthor() != null) {
                sb.append("Author: ").append(embed.getAuthor().getName()).append("\n");
            }

            if (embed.getFooter() != null) {
                sb.append("Footer: ").append(embed.getFooter().getText()).append("\n");
            }

            if (!embed.getFields().isEmpty()) {
                for (MessageEmbed.Field field : embed.getFields()) {
                    sb.append(field.getName())
                            .append(": ")
                            .append(field.getValue())
                            .append("\n");
                }
            }

            if (embed.getUrl() != null) {
                sb.append("URL: ").append(embed.getUrl()).append("\n");
            }

            sb.append("\n-----------\n\n"); // separator between embeds
        }

        return sb.toString().trim();
    }

}
