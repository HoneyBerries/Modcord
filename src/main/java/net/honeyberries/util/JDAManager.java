package net.honeyberries.util;

import net.dv8tion.jda.api.JDA;
import org.jetbrains.annotations.Nullable;

/**
 * Singleton manager for accessing the JDA bot instance globally.
 */
public class JDAManager {
    private static final JDAManager INSTANCE = new JDAManager();
    private JDA jda;

    private JDAManager() {
    }

    public static JDAManager getInstance() {
        return INSTANCE;
    }

    /**
     * Sets the JDA instance (called during bot initialization).
     * @param jda The JDA instance
     */
    public void setJDA(JDA jda) {
        this.jda = jda;
    }

    /**
     * Gets the JDA instance.
     * @return The JDA instance, or null if not initialized
     */
    @Nullable
    public JDA getJDA() {
        return jda;
    }
}

