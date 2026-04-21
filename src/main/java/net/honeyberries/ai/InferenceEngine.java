package net.honeyberries.ai;

import com.openai.client.OpenAIClientAsync;
import com.openai.client.okhttp.OpenAIOkHttpClientAsync;
import com.openai.errors.OpenAIException;
import com.openai.models.ResponseFormatJsonSchema;
import com.openai.models.chat.completions.ChatCompletionAssistantMessageParam;
import com.openai.models.chat.completions.ChatCompletionCreateParams;
import com.openai.models.chat.completions.ChatCompletionMessageParam;
import net.honeyberries.config.AppConfig;
import net.honeyberries.timeout.CircuitBreaker;
import net.honeyberries.timeout.RetryExecutor;
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
import java.util.concurrent.TimeUnit;

/**
 * Provides an asynchronous interface to OpenAI-compatible language models for inference.
 * <p>
 * Wraps every call in a {@link RetryExecutor} (3 attempts, 500 ms base delay) and a
 * {@link CircuitBreaker} (5 failures → open; 60 s reset) so transient network issues and
 * temporary endpoint outages degrade gracefully rather than silently swallowing errors.
 * <p>
 * Unlike the previous implementation, failures are now propagated as typed
 * {@link InferenceException} instances so callers can distinguish an AI error from a
 * legitimate empty response and act accordingly.
 */
public class InferenceEngine {

    /** Logger for inference request and error tracking. */
    private final Logger logger = LoggerFactory.getLogger(InferenceEngine.class);

    /** LLM model identifier (e.g., "gpt-4o", "moonshotai/Kimi-K2.5"). */
    private final String modelName;
    /** Async OpenAI API client for making completion requests. */
    private final OpenAIClientAsync openAIClient;

    /** Retries transient failures with exponential back-off. */
    private final RetryExecutor retryExecutor = new RetryExecutor(3, 500);
    /**
     * Circuit breaker: opens after 5 consecutive failures and attempts a probe after 60 s.
     * Prevents the scheduler from hammering a down endpoint with back-to-back requests.
     */
    private final CircuitBreaker circuitBreaker = new CircuitBreaker("AI-inference", 5, 60_000);

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
     * <p>
     * The call is guarded by a circuit breaker and retried up to 3 times with exponential
     * back-off on transient failures. If all retries are exhausted, or the circuit breaker
     * is OPEN, the returned future completes exceptionally with an {@link InferenceException}.
     * <p>
     * Callers must check for {@link InferenceException} in their {@code exceptionally} handler
     * and must <em>not</em> treat the result as a legitimate response if it is empty.
     *
     * @param messages       the list of chat messages; typically includes system prompt first, then user messages
     * @param responseFormat optional schema for structured JSON responses; if {@code null}, returns plain text
     * @return a {@code CompletableFuture} that resolves to the assistant message on success,
     *         or completes exceptionally with an {@link InferenceException} on failure
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

        ChatCompletionCreateParams params = builder.build();

        return CompletableFuture.supplyAsync(() -> {
            try {
                return retryExecutor.execute("AI inference", () ->
                        circuitBreaker.execute(() ->
                                openAIClient.chat().completions().create(params)
                                        .thenApply(completion -> completion.choices().stream()
                                                .findFirst()
                                                .map(choice -> choice.message().toParam())
                                                .orElseThrow(() -> new OpenAIException("No choices returned from LLM")))
                                        .get(AppConfig.getInstance().getAIRequestTimeout(), TimeUnit.SECONDS)
                        )
                );
            } catch (CircuitBreaker.CircuitOpenException e) {
                logger.warn("AI inference rejected — circuit breaker is OPEN: {}", e.getMessage());
                throw new InferenceException("Circuit breaker is OPEN, AI inference unavailable", e);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new InferenceException("AI inference interrupted", e);
            } catch (InferenceException e) {
                throw e;
            } catch (Exception e) {
                logger.error("AI inference failed after all retries: {}", e.getMessage(), e);
                throw new InferenceException("AI inference failed: " + e.getMessage(), e);
            }
        });
    }

    /**
     * Thrown when the inference engine cannot produce a response due to a network error,
     * API error, open circuit breaker, or exhausted retries. Callers should log this and
     * treat the moderation batch as un-processed rather than silently accepting an empty response.
     */
    public static class InferenceException extends RuntimeException {

        /**
         * Constructs a new exception with the supplied detail message.
         *
         * @param message descriptive error message, must not be {@code null}
         */
        public InferenceException(@NotNull String message) {
            super(Objects.requireNonNull(message, "message must not be null"));
        }

        /**
         * Constructs a new exception wrapping an underlying cause.
         *
         * @param message descriptive error message, must not be {@code null}
         * @param cause   root cause, may be {@code null}
         */
        public InferenceException(@NotNull String message, @Nullable Throwable cause) {
            super(Objects.requireNonNull(message, "message must not be null"), cause);
        }
    }
}
