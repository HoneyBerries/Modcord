package net.honeyberries.ai;

import com.openai.client.OpenAIClientAsync;
import com.openai.client.okhttp.OpenAIOkHttpClientAsync;
import com.openai.errors.OpenAIException;
import com.openai.models.ResponseFormatJsonSchema;
import com.openai.models.chat.completions.ChatCompletionAssistantMessageParam;
import com.openai.models.chat.completions.ChatCompletionCreateParams;
import com.openai.models.chat.completions.ChatCompletionMessageParam;
import io.github.resilience4j.decorators.Decorators;
import io.github.resilience4j.retry.Retry;
import io.github.resilience4j.retry.RetryConfig;
import net.honeyberries.config.AppConfig;
import net.honeyberries.util.TokenManager;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.time.Duration;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.atomic.AtomicReference;

/**
 * Provides asynchronous interface to OpenAI-compatible language models for inference.
 * Manages API client lifecycle, handles structured output formatting, and abstracts away client configuration.
 * Supports both unstructured text responses and structured JSON schema-based completions for moderation decisions.
 * <p>
 * Calls are retried with Resilience4j defaults. The time of the last success and last failure is tracked
 * for {@code /status health}.
 */
public class InferenceEngine {

    private static final Logger logger = LoggerFactory.getLogger(InferenceEngine.class);

    private final String modelName;
    /** Stored for log messages only. */

    private final String endpoint;

    /** OpenAI client for making API calls. */
    private final OpenAIClientAsync openAIClient;

    private final Retry retry;

    private final AtomicReference<Instant> lastSuccess = new AtomicReference<>();
    private final AtomicReference<Instant> lastFailure = new AtomicReference<>();

    /** Single daemon thread that schedules exponential back-off delays between retries. */
    private final ScheduledExecutorService retryScheduler;

    private static final InferenceEngine INSTANCE = new InferenceEngine();

    public InferenceEngine() {
        String apiKey = TokenManager.getOpenAIKey();
        this.endpoint = AppConfig.getInstance().getAIEndpoint();
        this.modelName = AppConfig.getInstance().getAIModelName();

        this.openAIClient = OpenAIOkHttpClientAsync.builder()
                .apiKey(apiKey)
                .baseUrl(endpoint)
                .timeout(Duration.of(AppConfig.getInstance().getAIRequestTimeout(), ChronoUnit.SECONDS))
                .build();

        this.retry = buildRetry();
        this.retryScheduler = Executors.newSingleThreadScheduledExecutor();

        logger.info("InferenceEngine initialized: endpoint={}, model={}", endpoint, modelName);
    }

    @NotNull
    public static InferenceEngine getInstance() {
        return INSTANCE;
    }

    /** @return when an inference call last succeeded, or {@code null} if none has since startup */
    @Nullable
    public Instant getLastSuccess() {
        return lastSuccess.get();
    }

    /** @return when an inference call last failed (after retries), or {@code null} if none has since startup */
    @Nullable
    public Instant getLastFailure() {
        return lastFailure.get();
    }

    /**
     * Sends a chat completion request to the language model.
     * <p>
     * The call is transparently retried (Resilience4j defaults) before the returned future fails.
     *
     * @param messages       the conversation so far; typically system prompt then user message
     * @param responseFormat optional JSON schema for structured output; {@code null} for plain text
     * @return a future that completes with the assistant's reply, or completes exceptionally on error
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

        return Decorators.ofCompletionStage(
                        () -> openAIClient.chat().completions().create(params)
                                .thenApply(completion -> completion.choices().stream()
                                        .findFirst()
                                        .map(choice -> choice.message().toParam())
                                        .orElseThrow(() -> new OpenAIException("No choices returned from LLM"))))
                .withRetry(retry, retryScheduler)
                .decorate()
                .get()
                .toCompletableFuture()
                .whenComplete((result, error) ->
                        (error == null ? lastSuccess : lastFailure).set(Instant.now()));
    }

    private Retry buildRetry() {
        RetryConfig config = RetryConfig.ofDefaults();
        Retry r = Retry.of("inference", config);

        r.getEventPublisher().onRetry(event -> logger.warn(
                "AI inference retry #{} after error: {}",
                event.getNumberOfRetryAttempts(),
                event.getLastThrowable() != null ? event.getLastThrowable().getMessage() : "unknown"));

        r.getEventPublisher().onError(event -> logger.error(
                "AI inference failed after {} attempt(s): {}",
                event.getNumberOfRetryAttempts(),
                event.getLastThrowable() != null ? event.getLastThrowable().getMessage() : "unknown"));

        return r;
    }
}
