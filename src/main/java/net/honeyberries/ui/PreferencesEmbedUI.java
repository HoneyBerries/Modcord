package net.honeyberries.ui;

import net.dv8tion.jda.api.EmbedBuilder;
import net.dv8tion.jda.api.components.actionrow.ActionRow;
import net.dv8tion.jda.api.components.buttons.Button;
import net.dv8tion.jda.api.components.buttons.ButtonStyle;
import net.dv8tion.jda.api.components.selections.EntitySelectMenu;
import net.dv8tion.jda.api.components.selections.StringSelectMenu;
import net.dv8tion.jda.api.entities.MessageEmbed;
import net.dv8tion.jda.api.entities.channel.ChannelType;
import net.honeyberries.datatypes.action.ActionType;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.preferences.GuildPreferences;
import net.honeyberries.preferences.PreferencesManager;
import org.jetbrains.annotations.NotNull;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class PreferencesEmbedUI {

    /**
     * Builds the settings embed for the given category.
     *
     * @param category the settings category ({@code "general"} or {@code "actions"})
     * @return a formatted {@link MessageEmbed}
     */
    @NotNull
    public static MessageEmbed buildSettingsEmbed(@NotNull String category) {
        Objects.requireNonNull(category, "category must not be null");
        String title = category.equals("general") ? "Guild Preferences: General" : "Guild Preferences: Automated Actions";
        return new EmbedBuilder()
                .setTitle(title)
                .setDescription("Configure your moderation settings below.")
                .setColor(0x5865F2)
                .build();
    }

    /**
     * Builds the action row components for the settings UI.
     *
     * <p>For {@code "general"} category, includes:</p>
     * <ul>
     *   <li>AI moderation toggle button</li>
     *   <li>Rules channel select menu</li>
     *   <li>Audit log channel select menu</li>
     *   <li>Category navigation menu</li>
     * </ul>
     *
     * <p>For {@code "actions"} category, includes:</p>
     * <ul>
     *   <li>Toggle buttons for each moderation action (WARN, DELETE, TIMEOUT, KICK, BAN)</li>
     *   <li>Category navigation menu</li>
     * </ul>
     *
     * @param guildId the guild ID
     * @param category the settings category ({@code "general"} or {@code "actions"})
     * @return a list of action rows for the message components
     */
    @NotNull
    public static List<ActionRow> buildSettingsComponents(@NotNull GuildID guildId, @NotNull String category) {
        Objects.requireNonNull(guildId, "guildId must not be null");
        Objects.requireNonNull(category, "category must not be null");
        GuildPreferences prefs = PreferencesManager.getInstance().getOrDefaultPreferences(guildId);
        List<ActionRow> rows = new ArrayList<>();

        if (category.equals("general")) {
            rows.add(buildRulesChannelSelectRow(prefs));
            rows.add(buildAuditChannelSelectRow(prefs));
        } else if (category.equals("actions")) {
            rows.add(buildAiToggleRow(prefs));
            rows.add(buildActionToggleRow(prefs));
        }

        rows.add(buildNavigationRow(category));
        return rows;
    }

    /**
     * Builds the AI moderation toggle button row.
     *
     * @param prefs the current guild preferences
     * @return an action row containing the AI toggle button
     */
    private static ActionRow buildAiToggleRow(@NotNull GuildPreferences prefs) {
        boolean aiEnabled = prefs.aiEnabled();
        return ActionRow.of(
                Button.primary("pref_ai_toggle",
                                "AI Moderation: " + (aiEnabled ? "ON" : "OFF"))
                        .withStyle(aiEnabled ? ButtonStyle.SUCCESS : ButtonStyle.DANGER)
        );
    }

    /**
     * Builds the rules channel select menu row.
     *
     * @param prefs the current guild preferences
     * @return an action row containing the rules channel entity select menu
     */
    private static ActionRow buildRulesChannelSelectRow(@NotNull GuildPreferences prefs) {
        EntitySelectMenu.Builder builder = EntitySelectMenu.create("pref_rules_channel",
                        EntitySelectMenu.SelectTarget.CHANNEL)
                .setPlaceholder("Select Rules Channel")
                .setChannelTypes(ChannelType.TEXT);
        if (prefs.rulesChannelID() != null) {
            builder.setDefaultValues(EntitySelectMenu.DefaultValue.channel(prefs.rulesChannelID().value()));
        }
        return ActionRow.of(builder.build());
    }

    /**
     * Builds the audit log channel select menu row.
     *
     * @param prefs the current guild preferences
     * @return an action row containing the audit log channel entity select menu
     */
    private static ActionRow buildAuditChannelSelectRow(@NotNull GuildPreferences prefs) {
        EntitySelectMenu.Builder builder = EntitySelectMenu.create("pref_audit_channel",
                        EntitySelectMenu.SelectTarget.CHANNEL)
                .setPlaceholder("Select Audit Log Channel")
                .setChannelTypes(ChannelType.TEXT);
        if (prefs.auditLogChannelId() != null) {
            builder.setDefaultValues(EntitySelectMenu.DefaultValue.channel(prefs.auditLogChannelId().value()));
        }
        return ActionRow.of(builder.build());
    }

    /**
     * Builds the moderation action toggle buttons row.
     *
     * @param prefs the current guild preferences
     * @return an action row containing toggle buttons for each action type
     */
    private static ActionRow buildActionToggleRow(@NotNull GuildPreferences prefs) {
        return ActionRow.of(
                makeActionButton(ActionType.WARN, prefs),
                makeActionButton(ActionType.DELETE, prefs),
                makeActionButton(ActionType.TIMEOUT, prefs),
                makeActionButton(ActionType.KICK, prefs),
                makeActionButton(ActionType.BAN, prefs)
        );
    }

    /**
     * Builds the category navigation menu row.
     *
     * @param currentCategory the currently selected category
     * @return an action row containing the category navigation string select menu
     */
    private static ActionRow buildNavigationRow(@NotNull String currentCategory) {
        Objects.requireNonNull(currentCategory, "currentCategory must not be null");
        return ActionRow.of(
                StringSelectMenu.create("pref_nav")
                        .addOption("General Settings", "general", "AI, Rules, Audit Logs")
                        .addOption("Automated Actions", "actions", "Toggles for Warn, Ban, etc.")
                        .setDefaultValues(currentCategory)
                        .build()
        );
    }

    /**
     * Creates a toggle button for a moderation action.
     *
     * <p>The button is styled green (SUCCESS) if enabled, red (DANGER) if disabled.</p>
     *
     * @param action the action type
     * @param prefs the current guild preferences
     * @return a styled button for the action
     */
    private static Button makeActionButton(@NotNull ActionType action, @NotNull GuildPreferences prefs) {
        Objects.requireNonNull(action, "action must not be null");
        Objects.requireNonNull(prefs, "prefs must not be null");
        boolean enabled = PreferencesManager.getInstance().getActionEnabled(prefs, action);
        ButtonStyle style = enabled ? ButtonStyle.SUCCESS : ButtonStyle.DANGER;
        return Button.primary("pref_action_" + action.name(), action.name())
                .withStyle(style);
    }

}
