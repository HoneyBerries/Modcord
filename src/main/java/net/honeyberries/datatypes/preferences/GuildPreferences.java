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
 * Immutable record — use {@link #toBuilder()} to derive modified copies.
 */
public record GuildPreferences(
        @NotNull  GuildID   guildId,
        boolean             aiEnabled,
        @Nullable ChannelID rulesChannelID,
        boolean             autoWarnEnabled,
        boolean             autoDeleteEnabled,
        boolean             autoTimeoutEnabled,
        boolean             autoKickEnabled,
        boolean             autoBanEnabled,
        @Nullable ChannelID auditLogChannelId
) {
    // ── Compact canonical constructor ────────────────────────────────────────

    public GuildPreferences {
        Objects.requireNonNull(guildId, "guildId must not be null");
    }

    // ── DB column map ─────────────────────────────────────────────────────────

    public static final @NotNull Map<ActionType, String> ACTION_FLAG_FIELDS = Map.ofEntries(
            Map.entry(ActionType.WARN,    "auto_warn_enabled"),
            Map.entry(ActionType.DELETE,  "auto_delete_enabled"),
            Map.entry(ActionType.TIMEOUT, "auto_timeout_enabled"),
            Map.entry(ActionType.KICK,    "auto_kick_enabled"),
            Map.entry(ActionType.BAN,     "auto_ban_enabled")
    );

    // ── Default factory ───────────────────────────────────────────────────────

    /**
     * Creates a {@link GuildPreferences} with all feature flags enabled and
     * no channel hooks set, ready to be refined via {@link #toBuilder()}.
     */
    public static @NotNull GuildPreferences defaults(@NotNull GuildID guildId) {
        return new Builder(guildId).build();
    }

    // ── Wither / builder bridge ───────────────────────────────────────────────

    /** Returns a {@link Builder} pre-populated with every field from this instance. */
    public @NotNull Builder toBuilder() {
        return new Builder(guildId)
                .aiEnabled(aiEnabled)
                .rulesChannelId(rulesChannelID)
                .autoWarnEnabled(autoWarnEnabled)
                .autoDeleteEnabled(autoDeleteEnabled)
                .autoTimeoutEnabled(autoTimeoutEnabled)
                .autoKickEnabled(autoKickEnabled)
                .autoBanEnabled(autoBanEnabled)
                .auditLogChannelId(auditLogChannelId);
    }

    // ── Convenience withers (one-liners via toBuilder) ────────────────────────

    public @NotNull GuildPreferences withAiEnabled(boolean v)              { return toBuilder().aiEnabled(v).build(); }
    public @NotNull GuildPreferences withRulesChannelId(@Nullable ChannelID v)    { return toBuilder().rulesChannelId(v).build(); }
    public @NotNull GuildPreferences withRulesChannelId(long v)            { return withRulesChannelId(new ChannelID(v)); }
    public @NotNull GuildPreferences withAutoWarnEnabled(boolean v)        { return toBuilder().autoWarnEnabled(v).build(); }
    public @NotNull GuildPreferences withAutoDeleteEnabled(boolean v)      { return toBuilder().autoDeleteEnabled(v).build(); }
    public @NotNull GuildPreferences withAutoTimeoutEnabled(boolean v)     { return toBuilder().autoTimeoutEnabled(v).build(); }
    public @NotNull GuildPreferences withAutoKickEnabled(boolean v)        { return toBuilder().autoKickEnabled(v).build(); }
    public @NotNull GuildPreferences withAutoBanEnabled(boolean v)         { return toBuilder().autoBanEnabled(v).build(); }
    public @NotNull GuildPreferences withAuditLogChannelId(@Nullable ChannelID v) { return toBuilder().auditLogChannelId(v).build(); }
    public @NotNull GuildPreferences withAuditLogChannelId(long v)         { return withAuditLogChannelId(new ChannelID(v)); }

    // ── Builder ───────────────────────────────────────────────────────────────

    public static final class Builder {

        // guildId is mandatory and immutable — set once in the constructor
        private final @NotNull GuildID guildId;

        private boolean             aiEnabled          = true;
        private @Nullable ChannelID rulesChannelId     = null;
        private boolean             autoWarnEnabled    = true;
        private boolean             autoDeleteEnabled  = true;
        private boolean             autoTimeoutEnabled = true;
        private boolean             autoKickEnabled    = true;
        private boolean             autoBanEnabled     = true;
        private @Nullable ChannelID auditLogChannelId  = null;

        public Builder(@NotNull GuildID guildId) {
            this.guildId = Objects.requireNonNull(guildId, "guildId must not be null");
        }

        public @NotNull Builder aiEnabled(boolean v)                        { aiEnabled = v;          return this; }
        public @NotNull Builder rulesChannelId(@Nullable ChannelID v)       { rulesChannelId = v;     return this; }
        public @NotNull Builder rulesChannelId(long v)                      { return rulesChannelId(new ChannelID(v)); }
        public @NotNull Builder autoWarnEnabled(boolean v)                  { autoWarnEnabled = v;    return this; }
        public @NotNull Builder autoDeleteEnabled(boolean v)                { autoDeleteEnabled = v;  return this; }
        public @NotNull Builder autoTimeoutEnabled(boolean v)               { autoTimeoutEnabled = v; return this; }
        public @NotNull Builder autoKickEnabled(boolean v)                  { autoKickEnabled = v;    return this; }
        public @NotNull Builder autoBanEnabled(boolean v)                   { autoBanEnabled = v;     return this; }
        public @NotNull Builder auditLogChannelId(@Nullable ChannelID v)    { auditLogChannelId = v;  return this; }
        public @NotNull Builder auditLogChannelId(long v)                   { return auditLogChannelId(new ChannelID(v)); }

        public @NotNull GuildPreferences build() {
            return new GuildPreferences(
                    guildId,
                    aiEnabled,
                    rulesChannelId,
                    autoWarnEnabled,
                    autoDeleteEnabled,
                    autoTimeoutEnabled,
                    autoKickEnabled,
                    autoBanEnabled,
                    auditLogChannelId
            );
        }
    }
}