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
public class PreferencesHelper {

    private final GuildPreferencesRepository preferencesRepo;

    private static final PreferencesHelper INSTANCE = new PreferencesHelper();

    /**
     * Constructs a new PreferencesHelper with the singleton preferences repository.
     */
    public PreferencesHelper() {
        this.preferencesRepo = GuildPreferencesRepository.getInstance();
    }

    @NotNull
    public static PreferencesHelper getInstance() {
        return INSTANCE;
    }

    /**
     * Parses a string representation of an action type and returns the corresponding {@link ActionType}.
     * This method is case-insensitive and trims any leading or trailing whitespace from the input string.
     *
     * @param actionStr the string representation of the action type to parse; must not be null
     * @return the corresponding {@code ActionType} if the input matches a defined action,
     *         or {@code null} if the input does not match any action type
     * @throws NullPointerException if {@code actionStr} is null
     */
    @Nullable
    public ActionType parseActionType(@NotNull String actionStr) {
        Objects.requireNonNull(actionStr, "actionStr must not be null");
        return switch (actionStr.toLowerCase().strip()) {
            case "warn" -> ActionType.WARN;
            case "timeout" -> ActionType.TIMEOUT;
            case "delete" -> ActionType.DELETE;
            case "kick" -> ActionType.KICK;
            case "ban" -> ActionType.BAN;
            default -> null;
        };
    }

    /**
     * Sets the enabled state for a specific action in guild preferences.
     *
     * @param prefs the guild preferences to update
     * @param actionType the type of action to update
     * @param enabled whether the action should be enabled
     * @return the updated guild preferences
     * @throws NullPointerException if prefs or actionType is null
     */
    @NotNull
    public GuildPreferences setActionEnabled(@NotNull GuildPreferences prefs, @NotNull ActionType actionType, boolean enabled) {
        Objects.requireNonNull(prefs, "prefs must not be null");
        Objects.requireNonNull(actionType, "actionType must not be null");

        return switch (actionType) {
            case WARN -> prefs.withAutoWarnEnabled(enabled);
            case TIMEOUT -> prefs.withAutoTimeoutEnabled(enabled);
            case DELETE -> prefs.withAutoDeleteEnabled(enabled);
            case KICK -> prefs.withAutoKickEnabled(enabled);
            case BAN -> prefs.withAutoBanEnabled(enabled);
            default -> prefs;
        };
    }

    /**
     * Gets the enabled state for a specific action in guild preferences.
     *
     * @param prefs the guild preferences to query
     * @param actionType the type of action to check
     * @return true if the action is enabled, false otherwise
     * @throws NullPointerException if prefs or actionType is null
     */
    public boolean getActionEnabled(@NotNull GuildPreferences prefs, @NotNull ActionType actionType) {
        Objects.requireNonNull(prefs, "prefs must not be null");
        Objects.requireNonNull(actionType, "actionType must not be null");

        return switch (actionType) {
            case WARN -> prefs.autoWarnEnabled();
            case TIMEOUT -> prefs.autoTimeoutEnabled();
            case DELETE -> prefs.autoDeleteEnabled();
            case KICK -> prefs.autoKickEnabled();
            case BAN -> prefs.autoBanEnabled();
            default -> false;
        };
    }

    /**
     * Updates a guild preference and returns success status.
     *
     * @param prefs the guild preferences to persist
     * @return true if the operation succeeded, false otherwise
     */
    public boolean updatePreferences(@NotNull GuildPreferences prefs) {
        Objects.requireNonNull(prefs, "prefs must not be null");
        return preferencesRepo.addOrUpdateGuildPreferences(prefs);
    }

    /**
     * Gets the current preferences for a guild, or defaults if not found.
     *
     * <p>This method is useful for operations that always need a valid GuildPreferences
     * object without null checks. Eliminates the common pattern of:
     * {@code currentPrefs != null ? currentPrefs : GuildPreferences.defaults(guildId)}
     *
     * @param guildId the guild ID to query
     * @return the guild preferences, or default preferences if not found
     * @throws NullPointerException if guildId is null
     */
    @NotNull
    public GuildPreferences getOrDefaultPreferences(@NotNull GuildID guildId) {
        Objects.requireNonNull(guildId, "guildId must not be null");
        GuildPreferences prefs = preferencesRepo.getGuildPreferences(guildId);
        return prefs != null ? prefs : GuildPreferences.defaults(guildId);
    }

    /**
     * Gets the current preferences for a guild.
     *
     * @param guildId the guild ID to query
     * @return the guild preferences, or null if not found
     */
    @Nullable
    public GuildPreferences getPreferences(@NotNull GuildID guildId) {
        Objects.requireNonNull(guildId, "guildId must not be null");
        return preferencesRepo.getGuildPreferences(guildId);
    }

}