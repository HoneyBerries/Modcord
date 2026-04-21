package net.honeyberries.ui;

import net.dv8tion.jda.api.EmbedBuilder;
import net.dv8tion.jda.api.entities.User;
import net.honeyberries.datatypes.discord.UserID;
import net.honeyberries.util.DiscordUtils;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;

import java.awt.Color;
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public class AppealEmbedUI {

    /**
     * Builds an embed notification for a new moderation appeal to be posted in the audit log channel.
     *
     * @param appellant the user who submitted the appeal
     * @param appealId the UUID of the appeal
     * @param actionId the UUID of the action being appealed, may be null
     * @param reason the appeal text
     * @return an embed builder ready to be built
     */
    @NotNull
    public static EmbedBuilder buildAppealNotificationEmbed(
            @NotNull User appellant,
            @NotNull UUID appealId,
            @Nullable UUID actionId,
            @NotNull String reason) {
        Objects.requireNonNull(appellant, "appellant must not be null");
        Objects.requireNonNull(appealId, "appealId must not be null");
        Objects.requireNonNull(reason, "reason must not be null");

        UserID userId = UserID.fromUser(appellant);
        EmbedBuilder embed = new EmbedBuilder()
                .setTitle("📋 New Moderation Appeal")
                .setColor(Color.CYAN)
                .setTimestamp(Instant.now())
                .addField("Appellant", DiscordUtils.userMention(userId), true)
                .addField("Appeal ID", "`" + appealId + "`", true);

        if (actionId != null) {
            embed.addField("Action ID", "`" + actionId + "`", true);
        }

        embed.addField("Reason", reason, false)
                .setThumbnail(appellant.getEffectiveAvatarUrl())
                .setFooter("Use /appeal close " + appealId + " to resolve", null);

        return embed;
    }

}
