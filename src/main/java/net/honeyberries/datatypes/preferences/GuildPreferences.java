package net.honeyberries.datatypes.preferences;

import net.honeyberries.datatypes.action.ActionType;
import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;

import java.util.Map;
import java.util.Objects;

/**
 * Persistent per-guild configuration values.
 * Immutable record version for reading from DB and passing through orchestration layers without mutation.
 * Encapsulates feature toggles and channel hooks so moderation behavior can be tailored per guild.
 */
public record GuildPreferences(
        @NotNull GuildID guildId,
        boolean aiEnabled,
        @Nullable ChannelID rulesChannelID,
        boolean autoWarnEnabled,
        boolean autoDeleteEnabled,
        boolean autoTimeoutEnabled,
        boolean autoKickEnabled,
        boolean autoBanEnabled,
        @Nullable ChannelID auditLogChannelId
) {
    /** Mapping of moderation actions to their corresponding database flag columns. */
    public static final @NotNull Map<ActionType, String> ACTION_FLAG_FIELDS = Map.ofEntries(
            Map.entry(ActionType.WARN, "auto_warn_enabled"),
            Map.entry(ActionType.DELETE, "auto_delete_enabled"),
            Map.entry(ActionType.TIMEOUT, "auto_timeout_enabled"),
            Map.entry(ActionType.KICK, "auto_kick_enabled"),
            Map.entry(ActionType.BAN, "auto_ban_enabled")
    );


    /**
     * Constructor with defaults.
     *
     * @param guildId guild that owns these preferences; must not be {@code null}
     * @throws NullPointerException if {@code guildId} is {@code null}
     */
    public GuildPreferences(@NotNull GuildID guildId) {
        this(
                guildId,
                true,               // aiEnabled default
                null,               // rulesChannelID default
                true,               // autoWarnEnabled
                true,               // autoDeleteEnabled
                true,               // autoTimeoutEnabled
                true,               // autoKickEnabled
                true,               // autoBanEnabled
                null                // auditLogChannelId default
        );
    }
}
