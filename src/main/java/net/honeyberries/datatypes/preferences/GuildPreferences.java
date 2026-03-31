package net.honeyberries.datatypes.preferences;

import net.honeyberries.datatypes.action.ActionType;
import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;

import java.util.Map;

/**
 * Persistent per-guild configuration values.
 * Immutable record version for reading from DB.
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
    public static final Map<ActionType, String> ACTION_FLAG_FIELDS = Map.ofEntries(
            Map.entry(ActionType.WARN, "auto_warn_enabled"),
            Map.entry(ActionType.DELETE, "auto_delete_enabled"),
            Map.entry(ActionType.TIMEOUT, "auto_timeout_enabled"),
            Map.entry(ActionType.KICK, "auto_kick_enabled"),
            Map.entry(ActionType.BAN, "auto_ban_enabled")
    );

    /**
     * Constructor with defaults.
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