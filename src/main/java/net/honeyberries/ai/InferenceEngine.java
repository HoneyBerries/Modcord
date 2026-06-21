package net.honeyberries.ai;

import com.openai.client.OpenAIClientAsync;
import com.openai.client.okhttp.OpenAIOkHttpClientAsync;
import com.openai.errors.OpenAIException;
import com.openai.models.ResponseFormatJsonSchema;
import com.openai.models.chat.completions.ChatCompletionAssistantMessageParam;
import com.openai.models.chat.completions.ChatCompletionCreateParams;
import com.openai.models.chat.completions.ChatCompletionMessageParam;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
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
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;

/**
 * Provides asynchronous interface to OpenAI-compatible language models for inference.
 * Manages API client lifecycle, handles structured output formatting, and abstracts away client configuration.
 * Supports both unstructured text responses and structured JSON schema-based completions for moderation decisions.
 * <p>
 * Resilience is handled by two Resilience4j decorators stacked as: circuit breaker (outer) → retry (inner).
 * Retries are transparent to the circuit breaker — all retry attempts exhausting counts as one failure,
 * not one per attempt. After enough failures the circuit opens and calls are rejected immediately until
 * the breaker enters half-open and a probe call succeeds.
 */
public class InferenceEngine {

    private static final Logger logger = LoggerFactory.getLogger(InferenceEngine.class);

    private final String modelName;
    /** Stored for log messages only. */
    private final String endpoint;
    private final OpenAIClientAsync openAIClient;

    /** Retry and failure mechanism */
    private final CircuitBreaker circuitBreaker;
    private final Retry retry;

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

        this.circuitBreaker = buildCircuitBreaker();
        this.retry = buildRetry();
        this.retryScheduler = Executors.newSingleThreadScheduledExecutor(r -> {
            Thread t = new Thread(r, "inference-retry-scheduler");
            t.setDaemon(true);
            return t;
        });

        logger.info("InferenceEngine initialized: endpoint={}, model={}", endpoint, modelName);
    }

    @NotNull
    public static InferenceEngine getInstance() {
        return INSTANCE;
    }

    /**
     * Returns the circuit breaker so callers (e.g. {@code /status health}) can inspect its state and metrics.
     *
     * @return the Resilience4j {@link CircuitBreaker} managing this engine's API calls
     */
    @NotNull
    public CircuitBreaker getCircuitBreaker() {
        return circuitBreaker;
    }

    /**
     * Sends a chat completion request to the language model.
     * <p>
     * The call is transparently retried (Resilience4j defaults) before the circuit breaker sees the combined
     * attempt as a single failure. If the circuit breaker is open, the returned future completes exceptionally
     * with {@link io.github.resilience4j.circuitbreaker.CallNotPermittedException} immediately — no network
     * call is made.
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
                .withCircuitBreaker(circuitBreaker)
                .decorate()
                .get()
                .toCompletableFuture();
    }

    /**
     * Builds and configures a circuit breaker for managing API calls related to AI inference.
     * The circuit breaker monitors the failure rate and uses Resilience4j configurations to transition
     * between states based on API performance. It is configured with thresholds, retry limits, and
     * behavior for handling state changes.
     * <p>
     * This method also sets up event listeners to log state transitions, such as when the circuit breaker
     * transitions to open, half-open, or closed states. These logs provide insights into API health and
     * the circuit breaker's decision-making process.
     *
     * @return a fully configured {@link CircuitBreaker} instance used for managing resilience in API calls
     */
    private CircuitBreaker buildCircuitBreaker() {
        CircuitBreakerConfig config = CircuitBreakerConfig.ofDefaults();

        CircuitBreaker cb = CircuitBreaker.of("inference", config);

        cb.getEventPublisher().onStateTransition(event -> {
            CircuitBreaker.StateTransition transition = event.getStateTransition();

            switch (transition.getToState()) {
                case OPEN -> logger.error(
                        "AI inference circuit breaker OPENED — endpoint {} is failing. " +
                        "Calls suppressed until circuit recovers.",
                        endpoint);

                case HALF_OPEN -> logger.info(
                        "AI inference circuit breaker half-open — probing endpoint {}.", endpoint);

                case CLOSED -> logger.info(
                        "AI inference circuit breaker CLOSED — endpoint {} is healthy again.", endpoint);

                default -> logger.info("AI inference circuit breaker state: {} → {}",
                        transition.getFromState(), transition.getToState());
            }
        });

        return cb;
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
