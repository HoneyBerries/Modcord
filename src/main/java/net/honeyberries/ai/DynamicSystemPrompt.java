package net.honeyberries.ai;

import com.openai.models.chat.completions.ChatCompletionMessageParam;
import com.openai.models.chat.completions.ChatCompletionSystemMessageParam;
import net.honeyberries.config.AppConfig;
import net.honeyberries.database.GuildRulesRepository;
import net.honeyberries.datatypes.content.GuildRules;
import net.honeyberries.datatypes.discord.GuildID;
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
    public ChatCompletionMessageParam createDynamicSystemPrompt(@NotNull GuildID guildId) {
        Objects.requireNonNull(guildId, "guildId must not be null");
        String template = AppConfig.getInstance().getSystemPromptTemplate();

        GuildRules guildRules = GuildRulesRepository.getInstance().getGuildRulesFromCache(guildId);
        String guildRulesText = (guildRules != null && guildRules.rulesText() != null && !guildRules.rulesText().isBlank())
            ? guildRules.rulesText()
            : AppConfig.getInstance().getGenericServerRules();

        return ChatCompletionMessageParam.ofSystem(
            ChatCompletionSystemMessageParam.builder()
                .content(
                    template.replace("<|SERVER_RULES_INJECT|>", guildRulesText)
                ).build()
        );
    }

}
