package net.honeyberries.preferences;

import net.honeyberries.database.GuildPreferencesRepository;
import net.honeyberries.datatypes.action.ActionType;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.preferences.GuildPreferences;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;

import java.util.Objects;

/**
 * Lightweight utility for guild preference operations.
 *
 * <p>Provides core helper methods for managing guild preferences and action state manipulation.
 */
public class PreferencesManager {

    private final GuildPreferencesRepository preferencesRepo;

    private static final PreferencesManager INSTANCE = new PreferencesManager();

    public PreferencesManager() {
        this.preferencesRepo = GuildPreferencesRepository.getInstance();
    }

    @NotNull
    public static PreferencesManager getInstance() {
        return INSTANCE;
    }

    // -------------------------------------------------------------------------
    // Action helpers
    // -------------------------------------------------------------------------



    /**
     * Returns a copy of {@code prefs} with the given action's enabled state updated.
     *
     * @param prefs      the guild preferences to update; must not be null
     * @param actionType the action to toggle; must not be null
     * @param enabled    the new enabled state
     * @return updated {@link GuildPreferences}
     */
    @NotNull
    public GuildPreferences setActionEnabled(
            @NotNull GuildPreferences prefs,
            @NotNull ActionType actionType,
            boolean enabled) {
        Objects.requireNonNull(prefs, "prefs must not be null");
        Objects.requireNonNull(actionType, "actionType must not be null");

        return switch (actionType) {
            case WARN    -> prefs.withAutoWarnEnabled(enabled);
            case TIMEOUT -> prefs.withAutoTimeoutEnabled(enabled);
            case DELETE  -> prefs.withAutoDeleteEnabled(enabled);
            case KICK    -> prefs.withAutoKickEnabled(enabled);
            case BAN     -> prefs.withAutoBanEnabled(enabled);
            default      -> prefs;
        };
    }

    /**
     * Returns whether a given action is enabled in the supplied preferences.
     *
     * @param prefs      the guild preferences to query; must not be null
     * @param actionType the action to check; must not be null
     * @return {@code true} if the action is enabled
     */
    public boolean getActionEnabled(
            @NotNull GuildPreferences prefs,
            @NotNull ActionType actionType) {
        Objects.requireNonNull(prefs, "prefs must not be null");
        Objects.requireNonNull(actionType, "actionType must not be null");

        return switch (actionType) {
            case WARN    -> prefs.autoWarnEnabled();
            case TIMEOUT -> prefs.autoTimeoutEnabled();
            case DELETE  -> prefs.autoDeleteEnabled();
            case KICK    -> prefs.autoKickEnabled();
            case BAN     -> prefs.autoBanEnabled();
            default      -> false;
        };
    }

    // -------------------------------------------------------------------------
    // Persistence helpers
    // -------------------------------------------------------------------------

    /**
     * Persists the given guild preferences.
     *
     * @param prefs the preferences to save; must not be null
     * @return {@code true} if the operation succeeded
     */
    public boolean updatePreferences(@NotNull GuildPreferences prefs) {
        Objects.requireNonNull(prefs, "prefs must not be null");
        return preferencesRepo.addOrUpdateGuildPreferences(prefs);
    }

    /**
     * Returns the current preferences for a guild, falling back to defaults if none are stored.
     *
     * <p>Eliminates the common {@code prefs != null ? prefs : GuildPreferences.defaults(guildId)}
     * pattern at every call site.
     *
     * @param guildId the guild to look up; must not be null
     * @return the stored preferences, or {@link GuildPreferences#defaults(GuildID)} if absent
     */
    @NotNull
    public GuildPreferences getOrDefaultPreferences(@NotNull GuildID guildId) {
        Objects.requireNonNull(guildId, "guildId must not be null");
        GuildPreferences prefs = preferencesRepo.getGuildPreferences(guildId);
        return prefs != null ? prefs : GuildPreferences.defaults(guildId);
    }

}