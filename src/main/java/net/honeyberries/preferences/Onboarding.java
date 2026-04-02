package net.honeyberries.preferences;

import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.channel.concrete.TextChannel;
import net.honeyberries.database.GuildPreferencesRepository;
import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.preferences.GuildPreferences;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.regex.Pattern;

/**
 * Handles first-time guild setup and channel resolution for Modcord.
 *
 * <p>On each bot startup (or per task cycle), {@link #setupGuild(Guild)} is
 * called for every guild the bot is in. It attempts to resolve the rules and
 * audit-log channels and persists whatever it finds to {@link GuildPreferencesRepository}.
 *
 * <p>Guilds for which <em>neither</em> channel can be resolved are added to an
 * in-memory {@code unresolvableGuilds} set so the task scheduler stops
 * retrying them every cycle. The set is cleared on bot restart, so a server
 * reconfiguration is always picked up after a redeploy. Individual entries can
 * also be cleared via {@link #clearUnresolvable(Guild)}.
 */
public class Onboarding {

    // ---------------------------------------------------------------
    // Singleton
    // ---------------------------------------------------------------

    private static final Onboarding INSTANCE = new Onboarding();

    private Onboarding() {}

    public static Onboarding getInstance() {
        return INSTANCE;
    }

    // ---------------------------------------------------------------
    // Constants
    // ---------------------------------------------------------------

    private static final Logger logger = LoggerFactory.getLogger(Onboarding.class);

    private static final Pattern RULES_PATTERN = Pattern.compile(
            "(?i)\\brules?\\b"
    );
    private static final Pattern AUDIT_PATTERN = Pattern.compile(
            "(?i)\\b(audit[- ]?log|mod[- ]?log)s?\\b"
    );

    // ---------------------------------------------------------------
    // State
    // ---------------------------------------------------------------

    /**
     * Guilds that have been permanently marked as unresolvable this runtime.
     * Prevents repeated backfill attempts on every task cycle for guilds that
     * will never succeed (e.g. ambiguous channels, no community setup).
     */
    private final Set<Long> unresolvableGuilds = ConcurrentHashMap.newKeySet();

    // ---------------------------------------------------------------
    // Public API
    // ---------------------------------------------------------------

    /**
     * Attempts to resolve the rules and audit-log channels for the given guild
     * and persists the result. Existing preferences are preserved — only unset
     * fields are filled in.
     *
     * @param guild the guild to set up
     * @return {@code true} if preferences were successfully persisted
     */
    public boolean setupGuild(@NotNull Guild guild) {
        GuildID guildID = GuildID.fromGuild(guild);
        GuildPreferencesRepository repository = GuildPreferencesRepository.getInstance();

        GuildPreferences preferences = repository.getGuildPreferences(guildID);
        if (preferences == null) {
            preferences = GuildPreferences.defaults(guildID);
        }

        preferences = applyRulesChannel(guild, preferences);
        preferences = applyAuditChannel(guild, preferences);

        if (preferences.rulesChannelID() == null && preferences.auditLogChannelId() == null) {
            logger.warn("[{}] Neither rules nor audit channel could be resolved — " +
                    "suppressing further backfill attempts until restart.", guild.getName());
            unresolvableGuilds.add(guild.getIdLong());
        }

        boolean persisted = repository.addOrUpdateGuildPreferences(preferences);
        if (!persisted) {
            logger.error("[{}] Failed to persist guild preferences.", guild.getName());
        }

        return persisted;
    }

    /**
     * Returns {@code true} if this guild has been determined to be unresolvable
     * this runtime, meaning {@link #setupGuild(Guild)} should be skipped.
     */
    public boolean isUnresolvable(@NotNull Guild guild) {
        return unresolvableGuilds.contains(guild.getIdLong());
    }

    /**
     * Clears the unresolvable cache entry for a specific guild so the next
     * task cycle retries resolution. Call this when an admin updates
     * preferences manually.
     */
    public void clearUnresolvable(@NotNull Guild guild) {
        unresolvableGuilds.remove(guild.getIdLong());
        logger.info("[{}] Cleared unresolvable cache entry — will retry on next cycle.", guild.getName());
    }

    // ---------------------------------------------------------------
    // Preference application
    // ---------------------------------------------------------------

    /**
     * Resolves the rules channel and returns updated preferences. If a rules
     * channel is already set, the existing mapping is preserved.
     */
    @NotNull
    private GuildPreferences applyRulesChannel(@NotNull Guild guild, @NotNull GuildPreferences preferences) {
        if (preferences.rulesChannelID() != null) {
            logger.debug("[{}] Keeping existing rules channel mapping.", guild.getName());
            return preferences;
        }

        TextChannel channel = resolveRulesChannel(guild);
        if (channel != null) {
            logger.info("[{}] Rules channel resolved: #{}", guild.getName(), channel.getName());
            return preferences.withRulesChannelId(ChannelID.fromChannel(channel));
        }

        logger.warn("[{}] No rules channel could be resolved — leaving unset.", guild.getName());
        return preferences;
    }

    /**
     * Resolves the audit-log channel and returns updated preferences. If an
     * audit channel is already set, the existing mapping is preserved.
     */
    @NotNull
    private GuildPreferences applyAuditChannel(@NotNull Guild guild, @NotNull GuildPreferences preferences) {
        if (preferences.auditLogChannelId() != null) {
            logger.debug("[{}] Keeping existing audit channel mapping.", guild.getName());
            return preferences;
        }

        TextChannel channel = resolveAuditChannel(guild);
        if (channel != null) {
            logger.info("[{}] Audit channel resolved: #{}", guild.getName(), channel.getName());
            return preferences.withAuditLogChannelId(ChannelID.fromChannel(channel));
        }

        logger.warn("[{}] No audit channel could be resolved — leaving unset.", guild.getName());
        return preferences;
    }

    // ---------------------------------------------------------------
    // Channel resolution
    // ---------------------------------------------------------------

    /**
     * Resolves the rules channel for a guild using the following priority:
     * <ol>
     *   <li>Guild's designated community rules channel.</li>
     *   <li>Regex match — if exactly one match, use it; if ambiguous, pick the
     *       best candidate via {@link #scoreRulesChannel(TextChannel)}.</li>
     *   <li>{@code null} — no safe fallback exists for rules channels.</li>
     * </ol>
     */
    @Nullable
    private TextChannel resolveRulesChannel(@NotNull Guild guild) {
        // 1. Community rules channel
        TextChannel communityRules = guild.getRulesChannel();
        if (communityRules != null) {
            logger.debug("[{}] Using community rules channel: #{}", guild.getName(), communityRules.getName());
            return communityRules;
        }

        // 2. Regex
        List<TextChannel> matches = guild.getTextChannels().stream()
                .filter(c -> RULES_PATTERN.matcher(c.getName()).find())
                .toList();

        if (matches.isEmpty()) {
            return null;
        }

        if (matches.size() == 1) {
            logger.debug("[{}] Rules channel found via regex: #{}", guild.getName(), matches.getFirst().getName());
            return matches.getFirst();
        }

        // Ambiguous — score and pick the best candidate
        TextChannel best = matches.stream()
                .max(Comparator.comparingInt(this::scoreRulesChannel))
                .orElse(null);

        logger.warn("[{}] Ambiguous rules channel — {} matches; selected #{} via heuristic scoring {}",
                guild.getName(),
                matches.size(),
                best != null ? best.getName() : "none",
                matches.stream().map(c -> c.getName() + "=" + scoreRulesChannel(c)).toList()
        );

        return best;
    }

    /**
     * Scores a candidate rules channel. Higher scores are more likely to be
     * the canonical rules channel.
     *
     * <ul>
     *   <li>+3 — exact name match ({@code "rules"})</li>
     *   <li>+2 — name starts with {@code "rules"}</li>
     *   <li>penalty — name length (shorter = more canonical)</li>
     *   <li>penalty — channel position (lower position = higher in sidebar = more prominent)</li>
     * </ul>
     */
    private int scoreRulesChannel(@NotNull TextChannel channel) {
        String name = channel.getName().toLowerCase();
        int score = 0;

        if (name.equals("rules"))         score += 3;
        else if (name.startsWith("rules")) score += 2;

        score -= name.length();
        score -= channel.getPosition();

        return score;
    }

    /**
     * Resolves the audit-log channel for a guild using the following priority:
     * <ol>
     *   <li>Guild's community safety alerts channel.</li>
     *   <li>Regex match — if exactly one match, use it; if ambiguous, fall
     *       back to the guild's default channel.</li>
     *   <li>{@code null}.</li>
     * </ol>
     */
    @Nullable
    private TextChannel resolveAuditChannel(@NotNull Guild guild) {
        // 1. Community safety/mod channel
        TextChannel safetyAlertsChannel = guild.getSafetyAlertsChannel();
        if (safetyAlertsChannel != null) {
            logger.debug("[{}] Using safety alerts channel: #{}", guild.getName(), safetyAlertsChannel.getName());
            return safetyAlertsChannel;
        }

        // 2. Regex
        List<TextChannel> matches = guild.getTextChannels().stream()
                .filter(c -> AUDIT_PATTERN.matcher(c.getName()).find())
                .toList();

        if (matches.isEmpty()) {
            return null;
        }

        if (matches.size() == 1) {
            logger.debug("[{}] Audit channel found via regex: #{}", guild.getName(), matches.getFirst().getName());
            return matches.getFirst();
        }

        // Ambiguous — fall back to the guild's default channel
        TextChannel defaultChannel = Objects.requireNonNull(guild.getDefaultChannel()).asTextChannel();
        logger.warn("[{}] Ambiguous audit channel — {} matches; falling back to default channel #{}: {}",
                guild.getName(),
                matches.size(),
                defaultChannel.getName(),
                matches.stream().map(TextChannel::getName).toList()
        );

        return defaultChannel;
    }
}