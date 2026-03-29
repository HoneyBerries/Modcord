package net.honeyberries.util;

import io.github.cdimascio.dotenv.Dotenv;

public class TokenManager {

    private static final Dotenv dotenv = Dotenv.configure()
            .filename(".env")
            .ignoreIfMissing() // avoids crash if .env doesn't exist
            .load();

    private static String getEnvVar(String key) {
        // Try .env first
        String value = dotenv.get(key);
        // If missing, try system environment variables
        if (value == null || value.isBlank()) {
            value = System.getenv(key);
        }
        if (value == null || value.isEmpty()) {
            throw new IllegalStateException(key + " is not set in .env or system environment variables");
        }
        return value;
    }

    public static String getDiscordBotToken() {
        return getEnvVar("DISCORD_BOT_TOKEN");
    }

    public static String getOpenAIKey() {
        return getEnvVar("OPENAI_API_KEY");
    }

    public static String getDBPassword() {
        return getEnvVar("POSTGRES_DB_PASSWORD");
    }
}