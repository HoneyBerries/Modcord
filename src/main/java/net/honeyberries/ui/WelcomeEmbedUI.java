package net.honeyberries.ui;

import net.dv8tion.jda.api.EmbedBuilder;
import net.dv8tion.jda.api.entities.MessageEmbed;
import net.honeyberries.datatypes.preferences.GuildPreferences;
import org.jetbrains.annotations.NotNull;

import java.awt.Color;
import java.util.Objects;

/**
 * Builds the welcome message Modcord posts when it joins a server, also shown by {@code /faq}.
 */
public final class WelcomeEmbedUI {

    private WelcomeEmbedUI() {}

    /**
     * Builds the welcome embed: what Modcord does, which defaults are already active, and what to do next.
     *
     * @param prefs the guild's preferences after onboarding (used to mention resolved channels)
     * @return the embed, never {@code null}
     */
    @NotNull
    public static MessageEmbed build(@NotNull GuildPreferences prefs) {
        Objects.requireNonNull(prefs, "prefs must not be null");

        String rules = prefs.rulesChannelID() != null
                ? "<#" + prefs.rulesChannelID().value() + ">"
                : "not found yet. Set one with `/preferences rules_channel`";
        String audit = prefs.auditLogChannelId() != null
                ? "<#" + prefs.auditLogChannelId().value() + ">"
                : "not set. Pick one with `/preferences audit_channel`";

        return new EmbedBuilder()
                .setTitle("👋 Thanks for adding Modcord!")
                .setColor(Color.CYAN)
                .setDescription("Modcord is an AI moderator. It reviews messages in batches, "
                        + "enforces your server's rules, and logs every action it takes.")
                .addField("Already set up for you",
                        "• Rules channel: " + rules + "\n"
                                + "• Audit log channel: " + audit + "\n"
                                + "• AI moderation is on with sensible defaults",
                        false)
                .addField("What to do next",
                        """
                                1. Run `/setup` to check permissions and role order. \
                                Drag Modcord's role above the roles it should moderate.
                                2. Make sure your rules are posted in the rules channel above.
                                3. Tune actions and channels with `/preferences`.
                                4. Use `/exclude` to skip trusted users, roles or channels.
                                5. Run `/help` to see every command.""",
                        false)
                .addField("Good to know",
                        "• Users can appeal actions with `/appeal submit`.\n"
                                + "• Staff can undo any action with `/rollback action`.",
                        false)
                .build();
    }
}
