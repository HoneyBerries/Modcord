package net.honeyberries.message;

import net.dv8tion.jda.api.entities.Message;
import net.dv8tion.jda.api.entities.MessageEmbed;

public class EmbedParser {

    public static String parseEmbed(Message message) {
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
