package net.honeyberries.ai;

import com.openai.client.OpenAIClientAsync;
import com.openai.client.okhttp.OpenAIOkHttpClientAsync;
import com.openai.errors.OpenAIException;
import com.openai.models.Reasoning;
import com.openai.models.ReasoningEffort;
import com.openai.models.responses.Response;
import com.openai.models.responses.ResponseCreateParams;
import com.openai.models.responses.ResponseFormatTextJsonSchemaConfig;
import com.openai.models.responses.ResponseInputItem;
import com.openai.models.responses.ResponseOutputMessage;
import com.openai.models.responses.ResponseTextConfig;
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
import java.util.concurrent.atomic.AtomicReference;

/**
 * Provides asynchronous interface to OpenAI-compatible language models (Responses API) for inference.
 * Manages API client lifecycle, handles structured output formatting, and abstracts away client configuration.
 * Supports both unstructured text responses and structured JSON schema-based completions for moderation decisions.
 * <p>
 * The time of the last success and last failure is tracked for {@code /status health}.
 */
public class InferenceEngine {

    private static final Logger logger = LoggerFactory.getLogger(InferenceEngine.class);

    private final String modelName;

    /** Value for the {@code reasoning.effort} request field, or {@code null} to use the model default. */
    @Nullable
    private final String reasoningEffort;
    /** Stored for log messages only. */

    private final String endpoint;

    /** OpenAI client for making API calls. */
    private final OpenAIClientAsync openAIClient;

    private final AtomicReference<Instant> lastSuccess = new AtomicReference<>();
    private final AtomicReference<Instant> lastFailure = new AtomicReference<>();

    private static final InferenceEngine INSTANCE = new InferenceEngine();

    public InferenceEngine() {
        String apiKey = TokenManager.getOpenAIKey();
        this.endpoint = AppConfig.getInstance().getAIEndpoint();
        this.modelName = AppConfig.getInstance().getAIModelName();
        this.reasoningEffort = AppConfig.getInstance().getAIReasoningEffort();

        this.openAIClient = OpenAIOkHttpClientAsync.builder()
                .apiKey(apiKey)
                .baseUrl(endpoint)
                .timeout(Duration.of(AppConfig.getInstance().getAIRequestTimeout(), ChronoUnit.SECONDS))
                .maxRetries(0)
                .build();

        logger.info("InferenceEngine initialized: endpoint={}, model={}, reasoningEffort={}", endpoint, modelName, reasoningEffort);
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

    /** @return when an inference call last failed , or {@code null} if none has since startup */
    @Nullable
    public Instant getLastFailure() {
        return lastFailure.get();
    }

    /**
     * Sends a request to the language model through the Responses API.
     * The request is stateless ({@code store=false}); nothing is retained server-side.
     *
     * @param instructions   the system prompt, or {@code null} for none
     * @param input          the input items (typically a single user message)
     * @param responseFormat optional JSON schema for structured output; {@code null} for plain text
     * @return a future that completes with the model's output text, or completes exceptionally on error
     *         (including a refusal, an incomplete response, or a response with no text)
     * @throws NullPointerException if {@code input} is {@code null}
     */
    @NotNull
    public CompletableFuture<String> generateResponse(
            @Nullable String instructions,
            @NotNull List<ResponseInputItem> input,
            @Nullable ResponseFormatTextJsonSchemaConfig responseFormat) {
        Objects.requireNonNull(input, "input must not be null");

        ResponseCreateParams.Builder builder = ResponseCreateParams.builder()
                .model(modelName)
                .inputOfResponse(input)
                .store(false);

        if (instructions != null) {
            builder.instructions(instructions);
        }

        if (responseFormat != null) {
            builder.text(ResponseTextConfig.builder().format(responseFormat).build());
        }

        if (reasoningEffort != null) {
            // ReasoningEffort.of() keeps provider-specific values the enum has no constant for.
            builder.reasoning(Reasoning.builder().effort(ReasoningEffort.of(reasoningEffort)).build());
        }

        return openAIClient.responses().create(builder.build())
                .thenApply(InferenceEngine::extractOutputText)
                .whenComplete((result, error) ->
                        (error == null ? lastSuccess : lastFailure).set(Instant.now()));
    }

    /**
     * Concatenates the text of every output message in the response.
     *
     * @throws OpenAIException if the response is incomplete, failed, was refused, or has no text
     */
    @NotNull
    private static String extractOutputText(@NotNull Response response) {
        response.error().ifPresent(error -> {
            throw new OpenAIException("LLM returned an error: " + error.message());
        });
        response.incompleteDetails().ifPresent(details -> {
            throw new OpenAIException("LLM response incomplete: " + details.reason().map(Object::toString).orElse("unknown"));
        });

        StringBuilder text = new StringBuilder();
        for (ResponseOutputMessage message : response.output().stream()
                .flatMap(item -> item.message().stream())
                .toList()) {
            for (ResponseOutputMessage.Content content : message.content()) {
                content.refusal().ifPresent(refusal -> {
                    throw new OpenAIException("LLM refused the request: " + refusal.refusal());
                });
                content.outputText().ifPresent(outputText -> text.append(outputText.text()));
            }
        }

        if (text.isEmpty()) {
            throw new OpenAIException("No output text returned from LLM");
        }
        return text.toString();
    }
}
