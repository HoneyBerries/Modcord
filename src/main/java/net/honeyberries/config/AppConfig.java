package net.honeyberries.config;

import org.jetbrains.annotations.NotNull;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.yaml.snakeyaml.Yaml;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.HashMap;
import java.util.Map;

/**
 * File-based accessor around the YAML-based application configuration.
 * <p>
 * The class caches contents of {@code ./config/app_config.yml}, exposes map-like
 * access helpers, and resolves AI-specific preferences.
 * Supports safe reload from disk at runtime.
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
     * @param configPath The path to the YAML configuration file
     */
    public AppConfig(@NotNull Path configPath) {
        this.configPath = configPath;
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
     * Re-reads the YAML file and replaces the in-memory cache.
     */
    public void reload() {
        this.data = new HashMap<>(loadFromDisk());
        this.cachedSystemPrompt = null;
        this.systemPromptLoaded = false;
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
        Object dbSettingsObj = data.get("database");
        if (dbSettingsObj instanceof Map) {
            @SuppressWarnings("unchecked")
            Map<String, Object> dbSettings = (Map<String, Object>) dbSettingsObj;
            Object value = dbSettings.get("url");
            if (value != null) {
                return value.toString();
            }
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
        Object dbSettingsObj = data.get("database");
        if (dbSettingsObj instanceof Map) {
            @SuppressWarnings("unchecked")
            Map<String, Object> dbSettings = (Map<String, Object>) dbSettingsObj;
            Object value = dbSettings.get("username");
            if (value != null) {
                return value.toString();
            }
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
        Object aiSettingsObj = data.get("ai_settings");
        if (aiSettingsObj instanceof Map) {
            @SuppressWarnings("unchecked")
            Map<String, Object> aiSettings = (Map<String, Object>) aiSettingsObj;
            Object value = aiSettings.get("base_url");
            if (value != null) {
                return value.toString();
            }
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
        Object aiSettingsObj = data.get("ai_settings");
        if (aiSettingsObj instanceof Map) {
            @SuppressWarnings("unchecked")
            Map<String, Object> aiSettings = (Map<String, Object>) aiSettingsObj;
            Object value = aiSettings.get("model_name");
            if (value != null) {
                return value.toString();
            }
        }
        throw new RuntimeException("AI model name not configured");
    }
    
    /**
     * Returns the API request timeout for AI API requests in seconds.
     * Default: Long.MAX_VALUE if not specified in config.
     * 
     * @return The timeout in seconds
     */
    public double getAIRequestTimeout() {
        Object aiSettingsObj = data.get("ai_settings");
        if (aiSettingsObj instanceof Map) {
            @SuppressWarnings("unchecked")
            Map<String, Object> aiSettings = (Map<String, Object>) aiSettingsObj;
            Object value = aiSettings.get("api_request_timeout");
            if (value instanceof Number) {
                return ((Number) value).doubleValue();
            }
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
        Object cacheConfigObj = data.get("cache");
        
        if (cacheConfigObj instanceof Map) {
            
            @SuppressWarnings("unchecked")
            Map<String, Object> cacheConfig = (Map<String, Object>) cacheConfigObj;
            Object value = cacheConfig.get("rules_cache_refresh");
            
            if (value instanceof Number) {
                return ((Number) value).longValue();
            }
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
        Object cacheConfigObj = data.get("cache");
        if (cacheConfigObj instanceof Map) {
            @SuppressWarnings("unchecked")
            Map<String, Object> cacheConfig = (Map<String, Object>) cacheConfigObj;
            Object value = cacheConfig.get("channel_guidelines_cache_refresh");
            if (value instanceof Number) {
                return ((Number) value).longValue();
            }
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
        Object moderationConfigObj = data.get("moderation");
        if (moderationConfigObj instanceof Map) {
            @SuppressWarnings("unchecked")
            Map<String, Object> moderationConfig = (Map<String, Object>) moderationConfigObj;
            Object value = moderationConfig.get("moderation_queue_duration");
            if (value instanceof Number) {
                return ((Number) value).doubleValue();
            }
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
        Object moderationConfigObj = data.get("moderation");
        if (moderationConfigObj instanceof Map) {
            @SuppressWarnings("unchecked")
            Map<String, Object> moderationConfig = (Map<String, Object>) moderationConfigObj;
            Object value = moderationConfig.get("num_history_context_messages");
            if (value instanceof Number) {
                return ((Number) value).longValue();
            }
        }
        throw new RuntimeException("Number of history context messages not configured");
    }


    public double getHistoryContextMaxAge() {
        Object moderationConfigObj = data.get("moderation");
        if (moderationConfigObj instanceof Map) {
            @SuppressWarnings("unchecked")
            Map<String, Object> moderationConfig = (Map<String, Object>) moderationConfigObj;
            Object value = moderationConfig.get("history_context_max_age");
            if (value instanceof Number) {
                return ((Number) value).doubleValue();
            }
        }
        throw new RuntimeException("History context max age not configured");
    }


    public static AppConfig getInstance() {
        return INSTANCE;
    }
}
