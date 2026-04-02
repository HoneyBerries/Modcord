package net.honeyberries.preferences;

import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.channel.concrete.TextChannel;
import net.honeyberries.database.GuildPreferencesRepository;
import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.preferences.GuildPreferences;
import org.slf4j.Logger;

import java.util.List;
import java.util.regex.Pattern;

public class Onboarding {

    public static final Onboarding INSTANCE = new Onboarding();
    private static final Logger logger = org.slf4j.LoggerFactory.getLogger(Onboarding.class);

    private static final Pattern RULES_PATTERN = Pattern.compile(
            "(?i)\\brules?\\b"
    );
    private static final Pattern AUDIT_PATTERN = Pattern.compile(
            "(?i)\\b(audit[- ]?log|mod[- ]?log)s?\\b"
    );

    public static Onboarding getInstance() {
        return INSTANCE;
    }

    // ---------------------------------------------------------------

    public boolean setupGuild(Guild guild) {
        GuildID guildID = GuildID.fromGuild(guild);
        GuildPreferences defaultPreferences = GuildPreferences.defaults(guildID);

        TextChannel rulesChannel = resolveRulesChannel(guild);
        TextChannel auditChannel = resolveAuditChannel(guild);

        if (rulesChannel != null) {
            logger.info("[{}] Rules channel resolved: #{}", guild.getName(), rulesChannel.getName());
            defaultPreferences = defaultPreferences.withRulesChannelId(ChannelID.fromChannel(rulesChannel));
        } else {
            logger.warn("[{}] No rules channel could be resolved — leaving unset.", guild.getName());
        }

        if (auditChannel != null) {
            logger.info("[{}] Audit channel resolved: #{}", guild.getName(), auditChannel.getName());
            defaultPreferences = defaultPreferences.withAuditLogChannelId(ChannelID.fromChannel(auditChannel));
        } else {
            logger.warn("[{}] No audit channel could be resolved — leaving unset.", guild.getName());
        }

        boolean persisted = GuildPreferencesRepository.getInstance().addOrUpdateGuildPreferences(defaultPreferences);
        if (!persisted) {
            logger.error("[{}] Failed to persist default guild preferences", guild.getName());
        }

        return persisted;
    }

    // ---------------------------------------------------------------

    /**
     * Resolution order:
     *   1. Guild's community rules channel (well-defined, set by server admins)
     *   2. Regex match — but ONLY if exactly one channel matches
     *   3. null
     */
    private TextChannel resolveRulesChannel(Guild guild) {

        // 1. Community rules channel
        TextChannel communityRules = guild.getRulesChannel();
        if (communityRules != null) {
            logger.debug("[{}] Using community rules channel: #{}", guild.getName(), communityRules.getName());
            return communityRules;
        }

        // 2. Regex — only accept an unambiguous single match
        List<TextChannel> regexMatches = guild.getTextChannels().stream()
                .filter(c -> RULES_PATTERN.matcher(c.getName()).find())
                .toList();

        if (regexMatches.size() == 1) {
            logger.debug("[{}] Rules channel found via regex: #{}", guild.getName(), regexMatches.getFirst().getName());
            return regexMatches.getFirst();
        }

        if (regexMatches.size() > 1) {
            logger.warn("[{}] Ambiguous rules channel — {} matches found via regex, leaving unset: {}",
                    guild.getName(),
                    regexMatches.size(),
                    regexMatches.stream().map(TextChannel::getName).toList()
            );
        }

        // 3. Unset
        return null;
    }

    // ---------------------------------------------------------------

    /**
     * Resolution order:
     *   1. Guild's community safety alerts channel (moderator-only, well-defined)
     *   2. Regex match on channel name
     *   3. Guild's general channel
     *   4. null
     */
    private TextChannel resolveAuditChannel(Guild guild) {

        // 1. Community safety/mod channel
        TextChannel safetyAlertsChannel = guild.getSafetyAlertsChannel();
        if (safetyAlertsChannel != null) {
            logger.debug("[{}] Using safety alerts channel: #{}", guild.getName(), safetyAlertsChannel.getName());
            return safetyAlertsChannel;
        }

        // 2. Regex match
        TextChannel regexMatch = guild.getTextChannels().stream()
                .filter(c -> AUDIT_PATTERN.matcher(c.getName()).find())
                .findFirst()
                .orElse(null);

        if (regexMatch != null) {
            logger.debug("[{}] Audit channel found via regex: #{}", guild.getName(), regexMatch.getName());
            return regexMatch;
        }

        // 3. General channel fallback
        TextChannel defaultChannel = guild.getDefaultChannel() instanceof TextChannel tc ? tc : null;
        if (defaultChannel != null) {
            logger.debug("[{}] Falling back to general channel for audit: #{}", guild.getName(), defaultChannel.getName());
            return defaultChannel;
        }

        // 4. Unset
        return null;
    }
}