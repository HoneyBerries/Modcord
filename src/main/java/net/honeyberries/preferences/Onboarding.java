package net.honeyberries.preferences;

import net.dv8tion.jda.api.Permission;
import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.channel.concrete.TextChannel;
import net.dv8tion.jda.api.requests.restaction.ChannelAction;
import net.honeyberries.database.repository.GuildPreferencesRepository;
import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.preferences.GuildPreferences;
import net.honeyberries.util.DiscordUtils;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.Comparator;
import java.util.EnumSet;
import java.util.List;
import java.util.Set;
import java.util.regex.Pattern;

/**
 * Handles first-time guild setup and channel resolution for Modcord.
 *
 * <p>On each bot startup (or per task cycle), {@link #setupGuild(Guild)} is
 * called for every guild the bot is in. It attempts to resolve the rules and
 * audit-log channels and persists whatever it finds to {@link GuildPreferencesRepository}.
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

    /** Name of the audit channel Modcord creates when none can be found. Must match {@link #AUDIT_PATTERN}. */
    private static final String AUDIT_CHANNEL_NAME = "modcord-audit-log";

    /**
     * Matches common rules/guidelines channel names.
     * Covers: rules, rule, guidelines, guideline, conduct, code-of-conduct, tos.
     */
    private static final Pattern RULES_PATTERN = Pattern.compile(
            "(?i)\\b(?:rules?|guidelines?|conduct|tos)\\b"
    );

    /**
     * Matches common moderation log channel names.
     * The {@code [- ]?} between segments allows for optional hyphens (Discord
     * convention) or no separator at all (e.g. "modlogs", "auditlog").
     *
     * <p>Covers: audit-log/s, mod-log/s, modlogs, moderation-log/s, staff-log/s,
     * admin-log/s, action-log/s, bot-log/s, case-log/s, punishment-log/s,
     * infraction-log/s and variants without hyphens.
     */
    private static final Pattern AUDIT_PATTERN = Pattern.compile(
            "(?i)\\b(?:audit|mod(?:eration)?|staff|admin|action|bot|case|punishment|infraction)[- ]?logs?\\b"
    );


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
    public synchronized boolean setupGuild(@NotNull Guild guild) {
        GuildID guildID = GuildID.fromGuild(guild);
        GuildPreferencesRepository repository = GuildPreferencesRepository.getInstance();

        GuildPreferences preferences = repository.getGuildPreferences(guildID);
        if (preferences == null) {
            preferences = GuildPreferences.defaults(guildID);
        }

        preferences = applyRulesChannel(guild, preferences);
        preferences = applyAuditChannel(guild, preferences);

        if (preferences.rulesChannelID() == null && preferences.auditLogChannelId() == null) {
            logger.warn("[{}] Neither rules nor audit channel could be resolved", guild.getName());
        }

        boolean persisted = repository.addOrUpdateGuildPreferences(preferences);
        if (!persisted) {
            logger.error("[{}] Failed to persist guild preferences.", guild.getName());
        }

        return persisted;
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

        logger.warn("[{}] Ambiguous rules channel — {} matches; selected #{} via heuristic scoring: {}",
                guild.getName(),
                matches.size(),
                best.getName(),
                matches.stream().map(c -> c.getName() + "=" + scoreRulesChannel(c)).toList()
        );

        return best;
    }

    /**
     * Resolves the audit-log channel for a guild using the following priority:
     * <ol>
     *   <li>Guild's community safety alerts channel.</li>
     *   <li>Regex match — if exactly one match, use it; if ambiguous, pick the
     *       best candidate via {@link #scoreAuditChannel(TextChannel)}.</li>
     *   <li>A newly created private channel (see {@link #createAuditChannel(Guild)}),
     *       or {@code null} if that fails.</li>
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
            // 3. Nothing suitable exists, so create one
            return createAuditChannel(guild);
        }

        if (matches.size() == 1) {
            logger.debug("[{}] Audit channel found via regex: #{}", guild.getName(), matches.getFirst().getName());
            return matches.getFirst();
        }

        // Ambiguous — score and pick the best candidate (mirrors rules resolution)
        TextChannel best = matches.stream()
                .max(Comparator.comparingInt(this::scoreAuditChannel))
                .orElse(null);

        logger.warn("[{}] Ambiguous audit channel — {} matches; selected #{} via heuristic scoring: {}",
                guild.getName(),
                matches.size(),
                best.getName(),
                matches.stream().map(c -> c.getName() + "=" + scoreAuditChannel(c)).toList()
        );

        return best;
    }

    /**
     * Creates a private audit channel. It is hidden from {@code @everyone} and visible to the bot and to
     * roles holding {@link DiscordUtils#MODCORD_ADMIN_PERMISSION}. The name matches {@link #AUDIT_PATTERN},
     * so later runs find it instead of creating another.
     *
     * @return the new channel, or {@code null} if Discord refused (for example, missing Manage Channels)
     */
    @Nullable
    private TextChannel createAuditChannel(@NotNull Guild guild) {
        Set<Permission> view = EnumSet.of(Permission.VIEW_CHANNEL);

        ChannelAction<TextChannel> action = guild.createTextChannel(AUDIT_CHANNEL_NAME)
                .addPermissionOverride(guild.getPublicRole(), null, view)
                .addMemberPermissionOverride(guild.getSelfMember().getIdLong(),
                        EnumSet.of(Permission.VIEW_CHANNEL, Permission.MESSAGE_SEND, Permission.MESSAGE_EMBED_LINKS),
                        null);

        guild.getRoles().stream()
                .filter(r -> !r.isPublicRole() && !r.isManaged() && r.hasPermission(DiscordUtils.MODCORD_ADMIN_PERMISSION))
                .forEach(r -> action.addRolePermissionOverride(r.getIdLong(), view, null));

        try {
            TextChannel created = action.complete();
            logger.info("[{}] Created audit channel #{}", guild.getName(), created.getName());
            return created;
        } catch (Exception e) {
            logger.warn("[{}] Could not create an audit channel: {}", guild.getName(), e.getMessage());
            return null;
        }
    }

    // ---------------------------------------------------------------
    // Channel scoring
    // ---------------------------------------------------------------

    /**
     * Scores a candidate rules channel. Higher scores indicate a more likely
     * canonical rules channel. Tiers are mutually exclusive — only the highest
     * matching tier contributes, preventing accidental score stacking.
     *
     * <ul>
     *   <li>Tier 1 (+10/+8/+7) — exact canonical names: {@code rules},
     *       {@code guidelines}, {@code conduct}, {@code tos}</li>
     *   <li>Tier 2 (+9/+7/+6) — strong compound forms: {@code server-rules},
     *       {@code guild-rules}; ends/starts with {@code -rules};
     *       starts with {@code rules}</li>
     *   <li>Tier 3 (+4/+3) — keyword present anywhere in the name</li>
     *   <li>Penalty — name length (shorter = more canonical) and sidebar
     *       position (lower index = higher in sidebar = more prominent)</li>
     * </ul>
     */
    private int scoreRulesChannel(@NotNull TextChannel channel) {
        String name = channel.getName().toLowerCase();
        int score = 0;

        // Tier 1 — exact canonical names
        if      (name.equals("rules"))       score += 10;
        else if (name.equals("guidelines"))  score += 8;
        else if (name.equals("conduct"))     score += 7;
        else if (name.equals("tos"))         score += 7;

        // Tier 2 — strong compound forms
        else if (name.equals("server-rules") || name.equals("guild-rules")) score += 9;
        else if (name.startsWith("rules-") || name.endsWith("-rules"))      score += 7;
        else if (name.startsWith("rules"))                                   score += 6;

        // Tier 3 — keyword present somewhere in the name
        else if (name.contains("rules"))      score += 4;
        else if (name.contains("guidelines")) score += 3;
        else if (name.contains("conduct"))    score += 3;

        // Penalise verbosity and lower sidebar position
        score -= name.length() / 3;
        score -= channel.getPosition() / 5;

        return score;
    }

    /**
     * Scores a candidate audit-log channel. Higher scores indicate a more
     * likely canonical mod/audit log. Tiers are mutually exclusive.
     *
     * <ul>
     *   <li>Tier 1 (+10/+9) — exact {@code mod-log}, {@code modlog},
     *       {@code audit-log}, {@code auditlog} and their {@code -logs} plurals</li>
     *   <li>Tier 2 (+7) — starts with the most common prefixes
     *       (mod-log*, audit-log*, moderation-log*)</li>
     *   <li>Tier 3 (+5/+4/+3) — contains recognised paired keywords
     *       (e.g. "mod" + "log", "staff" + "log")</li>
     *   <li>Penalty — name length only; sidebar position is omitted because
     *       staff/audit channels are often intentionally placed lower and
     *       penalising them by position would backfire</li>
     * </ul>
     */
    private int scoreAuditChannel(@NotNull TextChannel channel) {
        String name = channel.getName().toLowerCase();
        int score = 0;

        // Tier 1 — exact canonical names (singular and plural)
        if      (name.equals("mod-log")    || name.equals("modlog"))    score += 10;
        else if (name.equals("mod-logs")   || name.equals("modlogs"))   score += 9;
        else if (name.equals("audit-log")  || name.equals("auditlog"))  score += 10;
        else if (name.equals("audit-logs") || name.equals("auditlogs")) score += 9;

        // Tier 2 — starts with the most common prefixes
        else if (name.startsWith("mod-log")        || name.startsWith("modlog"))        score += 7;
        else if (name.startsWith("audit-log")      || name.startsWith("auditlog"))      score += 7;
        else if (name.startsWith("moderation-log") || name.startsWith("moderationlog")) score += 7;

        // Tier 3 — other recognised paired keyword combinations
        else if (name.contains("mod")        && name.contains("log")) score += 5;
        else if (name.contains("audit")      && name.contains("log")) score += 5;
        else if (name.contains("staff")      && name.contains("log")) score += 4;
        else if (name.contains("admin")      && name.contains("log")) score += 4;
        else if (name.contains("action")     && name.contains("log")) score += 3;
        else if (name.contains("punishment") && name.contains("log")) score += 3;
        else if (name.contains("case")       && name.contains("log")) score += 3;

        // Penalise verbosity only
        score -= name.length() / 4;

        return score;
    }
}