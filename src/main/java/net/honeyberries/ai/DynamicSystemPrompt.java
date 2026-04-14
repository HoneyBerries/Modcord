package net.honeyberries.ai;

import com.openai.models.chat.completions.ChatCompletionMessageParam;
import com.openai.models.chat.completions.ChatCompletionSystemMessageParam;
import net.honeyberries.config.AppConfig;
import net.honeyberries.database.GuildRulesRepository;
import net.honeyberries.datatypes.content.GuildRules;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.preferences.GuildPreferences;
import net.honeyberries.preferences.PreferencesManager;
import org.jetbrains.annotations.NotNull;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.Objects;

/**
 * Generates dynamic system prompts for AI inference by injecting guild-specific rules.
 * Retrieves guild rules from cache or falls back to generic rules, then substitutes them into a template string.
 * This ensures the AI model has contextual awareness of each guild's moderation policy during message evaluation.
 */
public class DynamicSystemPrompt {

    /** Logger for recording system prompt generation events. */
    private final Logger logger = LoggerFactory.getLogger(DynamicSystemPrompt.class);
    /** Singleton instance. */
    private static final DynamicSystemPrompt INSTANCE = new DynamicSystemPrompt();

    /**
     * Retrieves the singleton instance of this class.
     *
     * @return the singleton {@code DynamicSystemPrompt} instance
     */
    @NotNull
    public static DynamicSystemPrompt getInstance() {
        return INSTANCE;
    }

    /**
     * Constructs a dynamic system prompt by injecting guild-specific rules into a template.
     * Attempts to fetch the guild's custom rules from cache; if unavailable or blank, uses generic server rules.
     * The template is expected to contain the placeholder {@code <|SERVER_RULES_INJECT|>}.
     *
     * @param guildId the guild for which to create the prompt
     * @return a {@link ChatCompletionMessageParam} configured as a system message with injected rules
     * @throws NullPointerException if {@code guildId} is {@code null}
     */
    @NotNull
    public ChatCompletionSystemMessageParam createDynamicSystemPrompt(@NotNull GuildID guildId) {
        Objects.requireNonNull(guildId, "guildId must not be null");
        String template = AppConfig.getInstance().getSystemPromptTemplate();

        GuildRules guildRules = GuildRulesRepository.getInstance().getGuildRulesFromCache(guildId);
        String guildRulesText = (guildRules != null && guildRules.rulesText() != null && !guildRules.rulesText().isBlank())
            ? guildRules.rulesText()
            : AppConfig.getInstance().getGenericServerRules();

        GuildPreferences guildPreferences = PreferencesManager.getInstance().getOrDefaultPreferences(guildId);

        String allowedActions = buildAllowedActions(guildPreferences);

        return ChatCompletionSystemMessageParam.builder()
                .content(
                        template.replace("<|SERVER_RULES_INJECT|>", guildRulesText).replace("<|ALLOWED_ACTIONS_INJECT|>", allowedActions)
                ).build();
    }


    /**
     * Constructs a string listing the allowed actions based on the provided guild preferences.
     * Actions are formatted as a pipe-separated list (e.g., "null" | "warn" | "delete" | ...).
     * "null" is always included; other actions are included based on guild preference flags.
     *
     * @param guildPreferences the preferences of the guild specifying which actions are enabled
     * @return a pipe-separated string of allowed actions
     */
    @NotNull
    private static String buildAllowedActions(@NotNull GuildPreferences guildPreferences) {
        StringBuilder allowedActions = new StringBuilder();
        allowedActions.append("\"null\"");

        if (guildPreferences.autoWarnEnabled()) allowedActions.append(" | \"warn\"");
        if (guildPreferences.autoDeleteEnabled()) allowedActions.append(" | \"delete\"");
        if (guildPreferences.autoTimeoutEnabled()) allowedActions.append(" | \"timeout\"");
        if (guildPreferences.autoKickEnabled()) allowedActions.append(" | \"kick\"");
        if (guildPreferences.autoBanEnabled()) allowedActions.append(" | \"ban\"");

        return allowedActions.toString();
    }

}
