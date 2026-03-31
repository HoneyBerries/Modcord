package net.honeyberries.util;

import io.github.cdimascio.dotenv.Dotenv;
import org.jetbrains.annotations.NotNull;

import java.util.Objects;

/**
 * Centralized accessor for secrets required by the application (Discord, OpenAI, database).
 * Reads values from a `.env` file when present and falls back to system environment variables,
 * providing consistent error handling when required keys are missing.
 */
public final class TokenManager {

    private static final @NotNull Dotenv dotenv = Dotenv.configure()
            .filename(".env")
            .ignoreIfMissing() // avoids crash if .env doesn't exist
            .load();

    private TokenManager() {
        // Utility class
    }

    /**
     * Retrieves a non-blank environment variable from .env or the process environment.
     *
     * @param key name of the variable to resolve; must not be {@code null} or blank
     * @return resolved value
     * @throws IllegalStateException if the variable cannot be resolved or is blank
     * @throws NullPointerException  if {@code key} is {@code null}
     */
    @NotNull
    private static String getEnvVar(@NotNull String key) {
        Objects.requireNonNull(key, "key must not be null");
        String value = dotenv.get(key);
        if (value == null || value.isBlank()) {
            value = System.getenv(key);
        }
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(key + " is not set in .env or system environment variables");
        }
        return value;
    }

    /**
     * Loads the Discord bot token required to authenticate the JDA client.
     *
     * @return non-null Discord bot token
     * @throws IllegalStateException if the token is missing
     */
    @NotNull
    public static String getDiscordBotToken() {
        return getEnvVar("DISCORD_BOT_TOKEN");
    }

    /**
     * Loads the OpenAI API key used for inference requests.
     *
     * @return non-null OpenAI API key
     * @throws IllegalStateException if the key is missing
     */
    @NotNull
    public static String getOpenAIKey() {
        return getEnvVar("OPENAI_API_KEY");
    }

    /**
     * Loads the PostgreSQL password used by the application database user.
     *
     * @return non-null database password
     * @throws IllegalStateException if the password is missing
     */
    @NotNull
    public static String getDBPassword() {
        return getEnvVar("POSTGRES_DB_PASSWORD");
    }
}
