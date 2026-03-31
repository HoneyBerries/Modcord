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

public class DynamicSystemPrompt {

    private final Logger logger = LoggerFactory.getLogger(DynamicSystemPrompt.class);
    private static final DynamicSystemPrompt INSTANCE = new DynamicSystemPrompt();

    public static DynamicSystemPrompt getInstance() {
        return INSTANCE;
    }


    @NotNull
    public ChatCompletionMessageParam createDynamicSystemPrompt(GuildID guildId) {
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
