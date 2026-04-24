package net.honeyberries.ai;

import com.openai.client.OpenAIClientAsync;
import com.openai.client.okhttp.OpenAIOkHttpClientAsync;
import com.openai.errors.OpenAIException;
import com.openai.models.ResponseFormatJsonSchema;
import com.openai.models.chat.completions.ChatCompletionAssistantMessageParam;
import com.openai.models.chat.completions.ChatCompletionCreateParams;
import com.openai.models.chat.completions.ChatCompletionMessageParam;
import net.honeyberries.config.AppConfig;
import net.honeyberries.util.TokenManager;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.time.Duration;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.CompletableFuture;

/**
 * Provides asynchronous interface to OpenAI-compatible language models for inference.
 * Manages API client lifecycle, handles structured output formatting, and abstracts away client configuration.
 * Supports both unstructured text responses and structured JSON schema-based completions for moderation decisions.
 */
public class InferenceEngine {

    /** Logger for inference request and error tracking. */
    private final Logger logger = LoggerFactory.getLogger(InferenceEngine.class);

    /** LLM model identifier (e.g., "gpt-4", "gpt-3.5-turbo"). */
    private final String modelName;
    /** Async OpenAI API client for making completion requests. */
    private final OpenAIClientAsync openAIClient;

    /** Singleton instance. */
    private static final InferenceEngine INSTANCE = new InferenceEngine();

    /**
     * Constructs the InferenceEngine by initializing the OpenAI API client.
     * Loads API credentials and endpoint configuration from environment and app config.
     * Logs initialization details for debugging connection issues.
     */
    public InferenceEngine() {
        String apiKey = TokenManager.getOpenAIKey();
        String endpoint = AppConfig.getInstance().getAIEndpoint();
        this.modelName = AppConfig.getInstance().getAIModelName();

        this.openAIClient = OpenAIOkHttpClientAsync.builder()
                .apiKey(apiKey)
                .baseUrl(endpoint)
                .timeout(Duration.of(AppConfig.getInstance().getAIRequestTimeout(), ChronoUnit.SECONDS))
                .build();

        logger.info("InferenceEngine initialized with endpoint={}, model={}", endpoint, modelName);
    }

    /**
     * Retrieves the singleton instance of the inference engine.
     *
     * @return the singleton {@code InferenceEngine}
     */
    @NotNull
    public static InferenceEngine getInstance() {
        return INSTANCE;
    }

    /**
     * Sends a chat completion request to the language model.
     * Supports both unstructured text responses and structured JSON outputs via response format schema.
     * Handles errors gracefully by logging and returning null, allowing the caller to handle failures.
     *
     * @param messages the list of chat messages; typically includes system prompt first, then user messages
     * @param responseFormat optional schema for structured JSON responses; if {@code null}, returns plain text
     * @return a {@code CompletableFuture} that resolves to the assistant message, or {@code null} on error
     * @throws NullPointerException if {@code messages} is {@code null}
     */
    @NotNull
    public CompletableFuture<ChatCompletionAssistantMessageParam> generateResponse(
            @NotNull List<ChatCompletionMessageParam> messages,
            @Nullable ResponseFormatJsonSchema responseFormat) {
        Objects.requireNonNull(messages, "messages must not be null");

        ChatCompletionCreateParams.Builder builder = ChatCompletionCreateParams.builder()
                .model(modelName)
                .messages(messages);

        if (responseFormat != null) {
            builder.responseFormat(responseFormat);
        }

        return openAIClient.chat().completions().create(builder.build())
                .thenApply(completion -> completion.choices().stream()
                        .findFirst()
                        .map(choice -> choice.message().toParam())
                        .orElseThrow(() -> new OpenAIException("No choices returned from LLM")))
                .exceptionally(ex -> {
                    logger.error("Error generating LLM response: {}", ex.getMessage(), ex);
                    return ChatCompletionAssistantMessageParam.builder().content("").build();
                });
    }
}
