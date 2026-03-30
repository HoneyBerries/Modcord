package net.honeyberries.ai;

import com.openai.client.OpenAIClientAsync;
import com.openai.client.okhttp.OpenAIOkHttpClientAsync;
import com.openai.models.ResponseFormatJsonSchema;
import com.openai.models.chat.completions.ChatCompletion;
import com.openai.models.chat.completions.ChatCompletionCreateParams;
import com.openai.models.chat.completions.ChatCompletionMessageParam;
import net.honeyberries.config.AppConfig;
import net.honeyberries.util.TokenManager;
import org.jetbrains.annotations.Nullable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.List;
import java.util.concurrent.CompletableFuture;

public class InferenceEngine {

    private final Logger logger = LoggerFactory.getLogger(InferenceEngine.class);

    private final String modelName;
    private final OpenAIClientAsync openAIClient;

    private static final InferenceEngine INSTANCE = new InferenceEngine();

    public InferenceEngine() {
        String apiKey = TokenManager.getOpenAIKey();
        String endpoint = AppConfig.getInstance().getAIEndpoint();
        this.modelName = AppConfig.getInstance().getAIModelName();

        this.openAIClient = OpenAIOkHttpClientAsync.builder()
                .apiKey(apiKey)
                .baseUrl(endpoint)
                .build();

        logger.info("InferenceEngine initialized with endpoint={}, model={}", endpoint, modelName);
    }

    public static InferenceEngine getInstance() {
        return INSTANCE;
    }

    /**
     * Sends a chat completion request.
     *
     * @param messages       The list of messages (system prompt should be first if needed).
     * @param responseFormat The expected response format schema for structured output, or null.
     * @return A CompletableFuture resolving to the response text, or null on error.
     */
    public CompletableFuture<String> generateResponse(
            List<ChatCompletionMessageParam> messages,
            @Nullable ResponseFormatJsonSchema responseFormat) {

        ChatCompletionCreateParams.Builder builder = ChatCompletionCreateParams.builder()
                .model(modelName)
                .messages(messages);

        if (responseFormat != null) {
            builder.responseFormat(responseFormat);
        }

        return openAIClient.chat().completions().create(builder.build())
                .thenApply(this::extractResponseText)
                .exceptionally(e -> {
                    logger.error("Error during LLM inference: {}", e.getMessage(), e);
                    return null;
                });
    }

    @Nullable
    private String extractResponseText(ChatCompletion completion) {
        String response = completion.choices().stream()
                .findFirst()
                .flatMap(choice -> choice.message().content())
                .orElseGet(() -> {
                    logger.warn("No content in LLM response");
                    return null;
                });

        logger.debug("LLM response: \n\n{}", response);
        return response;
    }
}