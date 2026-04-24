package net.honeyberries.task;

import net.dv8tion.jda.api.JDA;
import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.Message;
import net.dv8tion.jda.api.entities.channel.Channel;
import net.dv8tion.jda.api.entities.channel.concrete.TextChannel;
import net.honeyberries.database.Database;
import net.honeyberries.database.repository.GuildPreferencesRepository;
import net.honeyberries.database.repository.GuildRulesRepository;
import net.honeyberries.datatypes.content.GuildRules;
import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.preferences.GuildPreferences;
import net.honeyberries.message.EmbedParser;
import net.honeyberries.discord.JDAManager;
import net.honeyberries.preferences.Onboarding;
import net.honeyberries.util.DiscordUtils;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.List;
import java.util.concurrent.ExecutionException;
import java.util.stream.Collectors;

/**
 * Task that periodically updates guild rules text for all guilds the bot is in.
 * This task goes through each guild and updates the rules_text while preserving
 * the rules_channel_id set by users.
 */
public class GuildRulesTask implements Runnable {

    private enum UpdateOutcome {
        UPDATED,
        SKIPPED,
        FAILED
    }

    private final Logger logger = LoggerFactory.getLogger(GuildRulesTask.class);

    /**
     * Runs this operation.
     */
    @Override
    public void run() {
        logger.info("GuildRulesTask started");

        if (!Database.getInstance().isHealthy()) {
            logger.warn("Skipping GuildRulesTask because database is unavailable");
            return;
        }

        JDA jda = JDAManager.getInstance().getJDA();

        try {
            // Collect outcomes from updateGuildRules for each guild
            List<UpdateOutcome> results = jda.getGuilds().parallelStream()
                    .map(this::updateGuildRules)
                    .toList();

            long updatedCount = results.stream().filter(outcome -> outcome == UpdateOutcome.UPDATED).count();
            long skippedCount = results.stream().filter(outcome -> outcome == UpdateOutcome.SKIPPED).count();
            long failedCount = results.stream().filter(outcome -> outcome == UpdateOutcome.FAILED).count();

            if (failedCount > 0) {
                logger.warn("GuildRulesTask completed with {} updated, {} skipped, {} failed out of {} guilds",
                        updatedCount, skippedCount, failedCount, results.size());
            } else {
                logger.info("GuildRulesTask completed with {} updated and {} skipped out of {} guilds",
                        updatedCount, skippedCount, results.size());
            }

        } catch (Exception e) {
            logger.error("Error in GuildRulesTask", e);
        }
    }

    /**
     * Updates the rules for a given guild by checking the current rules in the database, retrieving and
     * validating rules from Discord, and persisting the updated rules back to the database.
     * <p>
     * If the guild is not registered in the database, this method attempts to onboard it with default preferences.
     * If no rules channel is configured, the method sets an unconfigured state in the database.
     *
     * @param guild the guild whose rules need to be updated; must not be null
     * @return the outcome of the update operation, which can be one of UPDATED, SKIPPED, or FAILED
     */
    private UpdateOutcome updateGuildRules(@NotNull Guild guild) {
        try {
            GuildID guildId = GuildID.fromGuild(guild);

            // Ensure guild exists in guild preferences database before inserting guild rules
            // This prevents foreign key constraint violations
            if (!ensureGuildExists(guildId, guild)) {
                return UpdateOutcome.FAILED;
            }

            // Resolve rules channel ID with fallback chain: preferences → cached rules → onboarding backfill
            ChannelID rulesChannelID = resolveRulesChannelID(guildId, guild);

            if (rulesChannelID == null) {
                logger.debug("No rules channel configured for guild: {} ({}), storing unconfigured state", guild.getName(), guildId.value());
                if (!GuildRulesRepository.getInstance().addOrReplaceGuildRulesToDatabase(new GuildRules(guildId, null, null))) {
                    logger.warn("Failed to persist unconfigured rules state for guild: {} ({})", guild.getName(), guildId.value());
                    return UpdateOutcome.FAILED;
                }
                return UpdateOutcome.SKIPPED;
            }

            // Fetch and persist rules
            String updatedRules = getGuildRulesFromDiscord(guild, rulesChannelID);
            if (updatedRules == null || updatedRules.isBlank()) {
                logger.debug("No rules found for guild: {} ({}).", guild.getName(), guildId.value());
                return UpdateOutcome.SKIPPED;
            }

            GuildRules currentGuildRules = new GuildRules(guildId, rulesChannelID, updatedRules);
            if (GuildRulesRepository.getInstance().addOrReplaceGuildRulesToDatabase(currentGuildRules)) {
                logger.debug("Updated rules for guild: {} ({})", guild.getName(), guildId.value());
                return UpdateOutcome.UPDATED;
            } else {
                logger.warn("Failed to update rules for guild: {} ({})", guild.getName(), guildId.value());
                return UpdateOutcome.FAILED;
            }

        } catch (Exception e) {
            logger.error("Error updating rules for guild {}", guild.getId(), e);
            return UpdateOutcome.FAILED;
        }
    }

    /**
     * Ensures the guild exists in the database, onboarding if necessary.
     */
    private boolean ensureGuildExists(@NotNull GuildID guildId, @NotNull Guild guild) {
        GuildPreferences existing = GuildPreferencesRepository.getInstance().getGuildPreferences(guildId);
        if (existing != null) {
            return true;
        }

        logger.debug("Guild {} not found in database, onboarding with default preferences", guildId.value());
        boolean success = Onboarding.getInstance().setupGuild(guild);
        if (!success) {
            logger.error("Failed to onboard guild {}", guild.getName());
        }
        return success;
    }

    /**
     * Resolves rules channel ID with fallback chain: fresh preferences → cached rules → onboarding backfill.
     * Returns null if no channel can be resolved.
     */
    @Nullable
    private ChannelID resolveRulesChannelID(@NotNull GuildID guildId, @NotNull Guild guild) {
        // Try fresh preferences first
        GuildPreferences preferences = GuildPreferencesRepository.getInstance().getGuildPreferences(guildId);
        if (preferences != null && preferences.rulesChannelID() != null) {
            return preferences.rulesChannelID();
        }

        // Fall back to cached rules
        GuildRules cachedRules = GuildRulesRepository.getInstance().getGuildRulesFromCache(guildId);
        if (cachedRules != null && cachedRules.rulesChannelId() != null) {
            return cachedRules.rulesChannelId();
        }

        // Attempt onboarding backfill
        logger.debug("Rules channel missing for guild {} ({}), attempting onboarding backfill", guild.getName(), guildId.value());
        if (!Onboarding.getInstance().setupGuild(guild)) {
            logger.warn("Onboarding backfill failed for guild {} ({})", guild.getName(), guildId.value());
            return null;
        }

        // Check preferences again after onboarding
        preferences = GuildPreferencesRepository.getInstance().getGuildPreferences(guildId);
        return preferences != null ? preferences.rulesChannelID() : null;
    }

    @Nullable
    private String getGuildRulesFromDiscord(@NotNull Guild guild, @NotNull ChannelID rulesChannelId) {
        Channel rulesChannel = guild.getGuildChannelById(rulesChannelId.value());

        if (!(rulesChannel instanceof TextChannel rulesTextChannel)) {
            return null;
        }

        try {
            List<Message> messages = rulesTextChannel.getHistory()
                    .retrievePast(100)
                    .submit()
                    .get();

            return messages.reversed().stream()
                    .map(this::extractRuleText)
                    .filter(s -> !(s == null))
                    .collect(Collectors.joining("\n\n"));

        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            logger.warn("Interrupted while fetching rules for guild {}", guild.getId());
            return null;
        } catch (ExecutionException e) {
            if (e.getCause() != null && DiscordUtils.isPermissionFailure((Exception) e.getCause())) {
                logger.warn("No permission to fetch rules for guild {} — check bot permissions in the rules channel", guild.getId());
            } else {
                logger.warn("Failed to fetch rules for guild {}", guild.getId(), e);
            }
            return null;
        }
    }

    @Nullable
    private String extractRuleText(@NotNull Message message) {
        String content = message.getContentDisplay();
        String embed = EmbedParser.parseEmbed(message);

        boolean hasContent = !content.isBlank();
        boolean hasEmbed = !embed.isBlank();

        if (hasContent && hasEmbed) {
            return content + "\n" + embed;
        }
        else if (hasContent) {
            return content;
        }
        return hasEmbed ? embed : null;
    }


}