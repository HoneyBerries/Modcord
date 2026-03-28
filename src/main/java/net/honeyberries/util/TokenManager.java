package net.honeyberries.util;

import io.github.cdimascio.dotenv.Dotenv;

public class TokenManager {

    private static final Dotenv dotenv = Dotenv.configure()
            .filename(".env") // optional, defaults to .env
            .load();

    /**
     * Get the Discord bot token from .env
     */
    public static String getDiscordBotToken() {
        String token = dotenv.get("DISCORD_BOT_TOKEN");
        if (token == null || token.isEmpty()) {
            throw new IllegalStateException("DISCORD_BOT_TOKEN is not set in .env");
        }
        return token;
    }

    /**
     * Get the OpenAI API key from .env
     */
    public static String getOpenAIKey() {
        String key = dotenv.get("OPENAI_API_KEY");
        if (key == null || key.isEmpty()) {
            throw new IllegalStateException("OPENAI_API_KEY is not set in .env");
        }
        return key;
    }

    /**
     * Get the PostgreSQL database password from .env
     */
    public static String getDBPassword() {
        String password = dotenv.get("POSTGRES_DB_PASSWORD");
        if (password == null || password.isEmpty()) {
            throw new IllegalStateException("POSTGRES_DB_PASSWORD is not set in .env");
        }
        return password;
    }
}