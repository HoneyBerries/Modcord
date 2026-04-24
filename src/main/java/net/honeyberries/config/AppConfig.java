package net.honeyberries.config;

import org.jetbrains.annotations.NotNull;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.yaml.snakeyaml.Yaml;

import java.io.IOException;
import java.net.URI;
import java.net.URISyntaxException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

/**
 * File-based accessor around the YAML-based application configuration.
 * <p>
 * The class caches contents of {@code ./config/app_config.yml}, exposes map-like
 * access helpers, and resolves AI-specific preferences.
 * Supports safe reload from disk at runtime with startup-time validation of all
 * critical settings (durations, URLs, model names) to fail fast on misconfiguration.
 */
public class AppConfig {
    private static final Logger logger = LoggerFactory.getLogger(AppConfig.class);

    private static final Path CONFIG_PATH = Paths.get("./config/app_config.yml").toAbsolutePath();
    private static final Path SYSTEM_PROMPT_PATH = Paths.get("./config/system_prompt.md").toAbsolutePath();

    private final Path configPath;
    protected Map<String, Object> data;
    private String cachedSystemPrompt;
    private boolean systemPromptLoaded = false;

    private static final AppConfig INSTANCE = new AppConfig(CONFIG_PATH);

    /**
     * Creates a new AppConfig instance with the given configuration file path.
     * Immediately loads the configuration from disk.
     *
     * @param configPath the path to the YAML configuration file
     * @throws NullPointerException if {@code configPath} is {@code null}
     */
    public AppConfig(@NotNull Path configPath) {
        this.configPath = Objects.requireNonNull(configPath, "configPath must not be null");
        this.data = new HashMap<>();
        reload();
    }

    // --------------------------
    // Private helpers
    // --------------------------

    /**
     * Loads the YAML configuration from the disk.
     * Returns an empty map if the file is not found or parsing fails.
     *
     * @return The loaded configuration as a Map, or an empty map on error
     */
    @NotNull
    protected Map<String, Object> loadFromDisk() {
        try {
            String content = Files.readString(configPath, StandardCharsets.UTF_8);
            Yaml yaml = new Yaml();
            Map<String, Object> loaded = yaml.load(content);
            return loaded != null ? loaded : new HashMap<>();
        } catch (IOException e) {
            logger.error("Config file {} not found.", configPath, e);
            return new HashMap<>();
        } catch (Exception e) {
            logger.error("Failed to load config {}: {}", configPath, e.getMessage(), e);
            return new HashMap<>();
        }
    }

    // --------------------------
    // Public API
    // --------------------------

    /**
     * Reloads configuration from disk and returns the loaded mapping.
     * <p>
     * Re-reads the YAML file and replaces the in-memory cache. If the loaded
     * configuration contains any critical fields, they are validated eagerly so
     * downstream callers never see impossible values (negative durations, blank
     * URLs, malformed model names, etc.).
     */
    public void reload() {
        this.data = new HashMap<>(loadFromDisk());
        this.cachedSystemPrompt = null;
        this.systemPromptLoaded = false;

        if (!this.data.isEmpty()) {
            validate();
        }
    }

    /**
     * Validates the currently loaded configuration, failing fast with a descriptive
     * {@link ConfigValidationException} when a critical setting is missing, malformed,
     * or outside a sensible range.
     *
     * <p>Validation only runs when a configuration file was successfully loaded; an
     * empty map (typical for test fixtures that point at a non-existent file) is a
     * signal to skip validation so accessor-specific exceptions continue to fire.
     *
     * @throws ConfigValidationException if any required field is invalid
     */
    protected void validate() {
        validateDatabaseUrl();
        validateNonBlankString("database.username", getDatabaseUsernameOrNull());
        validateAiEndpoint();
        validateNonBlankString("ai_settings.model_name", getAIModelNameOrNull());
        validatePositive("ai_settings.api_request_timeout", getAIRequestTimeoutOrNull());
        validatePositive("cache.rules_cache_refresh", getRulesSyncIntervalOrNull());
        validatePositive("cache.channel_guidelines_cache_refresh", getGuidelinesSyncIntervalOrNull());
        validatePositive("moderation.moderation_queue_duration", getModerationQueueDurationOrNull());
        validateNonNegative("moderation.num_history_context_messages", getHistoryContextMaxMessagesOrNull());
        validatePositive("moderation.history_context_max_age", getHistoryContextMaxAgeOrNull());
    }

    /**
     * Ensures the configured database URL is a valid PostgreSQL JDBC URL.
     *
     * @throws ConfigValidationException if the URL is missing or malformed
     */
    private void validateDatabaseUrl() {
        String url = getDatabaseUrlOrNull();
        if (url == null || url.isBlank()) {
            throw new ConfigValidationException("database.url must be a non-blank JDBC URL");
        }
        if (!url.startsWith("jdbc:postgresql://")) {
            throw new ConfigValidationException("database.url must start with 'jdbc:postgresql://' (got '" + url + "')");
        }
    }

    /**
     * Ensures the configured AI endpoint is a syntactically valid URL.
     *
     * @throws ConfigValidationException if the endpoint is missing or malformed
     */
    private void validateAiEndpoint() {
        String endpoint = getAIEndpointOrNull();
        if (endpoint == null || endpoint.isBlank()) {
            throw new ConfigValidationException("ai_settings.base_url must be a non-blank URL");
        }
        try {
            URI uri = new URI(endpoint);
            if (uri.getScheme() == null || uri.getHost() == null) {
                throw new ConfigValidationException("ai_settings.base_url must include scheme and host (got '" + endpoint + "')");
            }
        } catch (URISyntaxException e) {
            throw new ConfigValidationException("ai_settings.base_url is not a valid URI: '" + endpoint + "'", e);
        }
    }

    /**
     * Ensures a string setting is present and not blank.
     *
     * @param name  fully qualified configuration key for error messages
     * @param value value returned from the accessor, may be {@code null}
     * @throws ConfigValidationException if {@code value} is {@code null} or blank
     */
    private void validateNonBlankString(@NotNull String name, String value) {
        if (value == null || value.isBlank()) {
            throw new ConfigValidationException(name + " must be a non-blank string");
        }
    }

    /**
     * Ensures a numeric setting is strictly greater than zero.
     *
     * @param name  fully qualified configuration key for error messages
     * @param value value returned from the accessor, may be {@code null}
     * @throws ConfigValidationException if {@code value} is {@code null} or non-positive
     */
    private void validatePositive(@NotNull String name, Number value) {
        if (value == null) {
            throw new ConfigValidationException(name + " must be configured");
        }
        if (value.doubleValue() <= 0) {
            throw new ConfigValidationException(name + " must be > 0 (got " + value + ")");
        }
    }

    /**
     * Ensures a numeric setting is greater than or equal to zero.
     *
     * @param name  fully qualified configuration key for error messages
     * @param value value returned from the accessor, may be {@code null}
     * @throws ConfigValidationException if {@code value} is {@code null} or negative
     */
    private void validateNonNegative(@NotNull String name, Number value) {
        if (value == null) {
            throw new ConfigValidationException(name + " must be configured");
        }
        if (value.doubleValue() < 0) {
            throw new ConfigValidationException(name + " must be >= 0 (got " + value + ")");
        }
    }

    // --------------------------
    // High-level shortcuts
    // --------------------------

    /**
     * Returns the configured server rules_text as a string (or empty string).
     * <p>
     * The value is coerced to a string so callers can safely embed it into
     * prompts without additional checks.
     *
     * @return The server rules_text string, or empty string if not configured
     */
    @NotNull
    public String getGenericServerRules() {
        Object value = data.get("generic_server_rules");

        if (value != null) {
            return value.toString();
        }

        throw new RuntimeException("Generic server rules not configured");
    }

    /**
     * Returns the configured default channel guidelinesText as a string (or empty string).
     * <p>
     * The value is coerced to a string so callers can safely embed it into
     * prompts without additional checks.
     *
     * @return The channel guidelinesText string, or empty string if not configured
     */
    @NotNull
    public String getGenericChannelGuidelines() {
        Object value = data.get("generic_channel_guidelines");

        if (value != null) {
            return value.toString();
        }

        throw new RuntimeException("Default channel guidelinesText not configured");
    }

    /**
     * Returns the configured system prompt template from system_prompt.md file.
     * <p>
     * Lazily loads and caches the system prompt from the dedicated system_prompt.md file.
     *
     * @return The system prompt template
     */
    @NotNull
    public String getSystemPromptTemplate() {
        if (systemPromptLoaded) {
            if (cachedSystemPrompt != null) {
                return cachedSystemPrompt;
            }
            throw new RuntimeException("System prompt template not found");
        }

        try {
            cachedSystemPrompt = Files.readString(SYSTEM_PROMPT_PATH, StandardCharsets.UTF_8);
            systemPromptLoaded = true;
            return cachedSystemPrompt;
        } catch (IOException e) {
            systemPromptLoaded = true;
            logger.error("System prompt file {} not found.", SYSTEM_PROMPT_PATH, e);
            throw new RuntimeException("System prompt template not found", e);
        } catch (Exception e) {
            systemPromptLoaded = true;
            logger.error("Failed to load system prompt {}: {}", SYSTEM_PROMPT_PATH, e.getMessage(), e);
            throw new RuntimeException("Failed to load system prompt", e);
        }
    }

    // --------------------------
    // Database Settings accessors
    // --------------------------

    /**
     * Returns the PostgreSQL JDBC URL.
     * Default: "jdbc:postgresql://localhost:5432/modcord"
     *
     * @return The PostgreSQL JDBC URL
     */
    @NotNull
    public String getDatabaseUrl() {
        String value = getDatabaseUrlOrNull();
        if (value != null) {
            return value;
        }
        throw new RuntimeException("Database URL not configured");
    }

    /**
     * Returns the PostgreSQL database username.
     * Default: "modcord_user"
     *
     * @return The database username
     */
    @NotNull
    public String getDatabaseUsername() {
        String value = getDatabaseUsernameOrNull();
        if (value != null) {
            return value;
        }
        throw new RuntimeException("Database username not configured");
    }

    // --------------------------
    // AI Settings accessors
    // --------------------------

    /**
     * Returns the OpenAI-compatible API base URL.
     * Default: <a href="http://localhost:8000/v1">http://localhost:8000/v1</a>
     *
     * @return The API endpoint URL
     */
    @NotNull
    public String getAIEndpoint() {
        String value = getAIEndpointOrNull();
        if (value != null) {
            return value;
        }
        throw new RuntimeException("AI endpoint not configured");
    }

    /**
     * Returns the model name/identifier to use for inference.
     * Default: empty string
     *
     * @return The model name
     */
    @NotNull
    public String getAIModelName() {
        String value = getAIModelNameOrNull();
        if (value != null) {
            return value;
        }
        throw new RuntimeException("AI model name not configured");
    }

    /**
     * Returns the API request timeout for AI API requests in seconds.
     * Default: Long.MAX_VALUE if not specified in config.
     *
     * @return The timeout in seconds
     */
    public long getAIRequestTimeout() {
        Long value = getAIRequestTimeoutOrNull();
        if (value != null) {
            return value;
        }
        throw new RuntimeException("AI request timeout not configured");
    }

    /**
     * Returns the server rules_text sync interval in seconds.
     * <p>
     * This is the interval at which server rules_text are synced from Discord.
     * Default is never (INFINITY).
     *
     * @return The sync interval in seconds, or INFINITY if not configured
     */
    public long getRulesSyncInterval() {
        Long value = getRulesSyncIntervalOrNull();
        if (value != null) {
            return value;
        }
        throw new RuntimeException("Rules cache refresh not configured");
    }

    /**
     * Returns the channel guidelinesText sync interval in seconds.
     * <p>
     * This is the interval at which channel guidelinesText are synced from Discord.
     * Default is never (INFINITY).
     *
     * @return The sync interval in seconds, or INFINITY if not configured
     */
    public long getGuidelinesSyncInterval() {
        Long value = getGuidelinesSyncIntervalOrNull();
        if (value != null) {
            return value;
        }
        throw new RuntimeException("Channel guidelinesText cache refresh not configured");
    }

    /**
     * Returns the moderation queue window in seconds.
     * <p>
     * Messages received within this window are grouped for batch moderation.
     * Default is 15 seconds.
     *
     * @return The batch window in seconds
     */
    public double getModerationQueueDuration() {
        Double value = getModerationQueueDurationOrNull();
        if (value != null) {
            return value;
        }
        throw new RuntimeException("Moderation queue duration not configured");
    }

    /**
     * Returns the number of recent messages to fetch for context.
     * <p>
     * Provides context for violations. Default is 0 messages.
     *
     * @return The number of context messages to fetch
     */
    public long getHistoryContextMaxMessages() {
        Long value = getHistoryContextMaxMessagesOrNull();
        if (value != null) {
            return value;
        }
        throw new RuntimeException("Number of history context messages not configured");
    }

    /**
     * Returns the number of seconds to retain message history for context during moderation decisions.
     * Older messages beyond this age are excluded from context when evaluating violations.
     * Default is 0 seconds.
     *
     * @return the maximum age of context messages in seconds
     */
    public double getHistoryContextMaxAge() {
        Double value = getHistoryContextMaxAgeOrNull();
        if (value != null) {
            return value;
        }
        throw new RuntimeException("History context max age not configured");
    }

    /**
     * Returns the maximum number of messages held per guild in-memory before the
     * oldest messages are dropped to apply backpressure against runaway activity.
     * <p>
     * Defaults to 1000 when not configured — large enough to comfortably handle
     * most busy servers while bounding memory usage.
     *
     * @return the per-guild message queue cap, always > 0
     */
    public int getMaxQueueSizePerGuild() {
        Integer value = readIntSetting("moderation", "max_queue_size_per_guild");
        int effective = value != null ? value : 1000;
        return Math.max(1, effective);
    }

    /**
     * Returns the timeout in seconds applied when this process performs blocking
     * calls against Discord (member lookups, history fetches, action applications).
     * <p>
     * Defaults to 30 seconds to avoid stalling the processing thread indefinitely
     * if Discord becomes slow or unavailable.
     *
     * @return the Discord blocking call timeout in seconds, always > 0
     */
    public long getDiscordRequestTimeout() {
        Long value = readLongSetting("moderation", "discord_request_timeout");
        long effective = value != null ? value : 30L;
        return Math.max(1L, effective);
    }

    // --------------------------
    // Nullable accessors (used by validation)
    // --------------------------

    private String getDatabaseUrlOrNull() {
        return readStringSetting("database", "url");
    }

    private String getDatabaseUsernameOrNull() {
        return readStringSetting("database", "username");
    }

    private String getAIEndpointOrNull() {
        return readStringSetting("ai_settings", "base_url");
    }

    private String getAIModelNameOrNull() {
        return readStringSetting("ai_settings", "model_name");
    }

    private Long getAIRequestTimeoutOrNull() {
        return readLongSetting("ai_settings", "api_request_timeout");
    }

    private Long getRulesSyncIntervalOrNull() {
        return readLongSetting("cache", "rules_cache_refresh");
    }

    private Long getGuidelinesSyncIntervalOrNull() {
        return readLongSetting("cache", "channel_guidelines_cache_refresh");
    }

    private Double getModerationQueueDurationOrNull() {
        return readDoubleSetting("moderation", "moderation_queue_duration");
    }

    private Long getHistoryContextMaxMessagesOrNull() {
        return readLongSetting("moderation", "num_history_context_messages");
    }

    private Double getHistoryContextMaxAgeOrNull() {
        return readDoubleSetting("moderation", "history_context_max_age");
    }

    private String readStringSetting(@NotNull String section, @NotNull String key) {
        Map<String, Object> sectionData = readSection(section);
        if (sectionData == null) {
            return null;
        }
        Object value = sectionData.get(key);
        return value != null ? value.toString() : null;
    }

    private Long readLongSetting(@NotNull String section, @NotNull String key) {
        Map<String, Object> sectionData = readSection(section);
        if (sectionData == null) {
            return null;
        }
        Object value = sectionData.get(key);
        return value instanceof Number number ? number.longValue() : null;
    }

    private Integer readIntSetting(@NotNull String section, @NotNull String key) {
        Long value = readLongSetting(section, key);
        return value != null ? Math.toIntExact(value) : null;
    }

    private Double readDoubleSetting(@NotNull String section, @NotNull String key) {
        Map<String, Object> sectionData = readSection(section);
        if (sectionData == null) {
            return null;
        }
        Object value = sectionData.get(key);
        return value instanceof Number number ? number.doubleValue() : null;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> readSection(@NotNull String section) {
        Object sectionObj = data.get(section);
        if (sectionObj instanceof Map<?, ?>) {
            return (Map<String, Object>) sectionObj;
        }
        return null;
    }

    /**
     * Retrieves the singleton instance of the application configuration.
     * Configuration is loaded from disk on first access and can be reloaded via {@link #reload()}.
     *
     * @return the singleton {@code AppConfig} instance
     */
    @NotNull
    public static AppConfig getInstance() {
        return INSTANCE;
    }

    /**
     * Thrown when {@link AppConfig#validate()} detects an invalid setting at
     * startup (missing required field, negative duration, malformed URL, etc.).
     * Callers should treat this as a fatal configuration error.
     */
    public static class ConfigValidationException extends RuntimeException {

        /**
         * Constructs a new exception with the supplied detail message.
         *
         * @param message descriptive error message, must not be {@code null}
         */
        public ConfigValidationException(@NotNull String message) {
            super(Objects.requireNonNull(message, "message must not be null"));
        }

        /**
         * Constructs a new exception wrapping an underlying cause.
         *
         * @param message descriptive error message, must not be {@code null}
         * @param cause   root cause, must not be {@code null}
         */
        public ConfigValidationException(@NotNull String message, @NotNull Throwable cause) {
            super(Objects.requireNonNull(message, "message must not be null"),
                    Objects.requireNonNull(cause, "cause must not be null"));
        }
    }
}
