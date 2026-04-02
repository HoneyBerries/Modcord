package net.honeyberries.task;

import net.dv8tion.jda.api.JDA;
import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.Message;
import net.dv8tion.jda.api.entities.channel.Channel;
import net.dv8tion.jda.api.entities.channel.concrete.TextChannel;
import net.honeyberries.database.Database;
import net.honeyberries.database.GuildPreferencesRepository;
import net.honeyberries.database.GuildRulesRepository;
import net.honeyberries.datatypes.content.GuildRules;
import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.preferences.GuildPreferences;
import net.honeyberries.message.EmbedParser;
import net.honeyberries.discord.JDAManager;
import net.honeyberries.preferences.Onboarding;
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
     * Updates the rules text for a specific guild.
     * The rules_channel_id is preserved and only the rules_text is updated.
     *
     * @param guild The guild to update rules for
     */
    private UpdateOutcome updateGuildRules(Guild guild) {
        try {
            GuildID guildId = GuildID.fromGuild(guild);

            // Ensure guild exists in guild_preferences table before inserting guild rules
            // This prevents foreign key constraint violations
            GuildPreferences existingPreferences = GuildPreferencesRepository.getInstance()
                .getGuildPreferences(guildId);
            
            if (existingPreferences == null) {
                logger.debug("Guild {} not found in database, onboarding with    default preferences", guildId.value());

                boolean success = Onboarding.getInstance().setupGuild(guild);
                if (!success) {
                    logger.error("Failed to onboard guild {}", guild.getName());
                    return UpdateOutcome.FAILED;
                }
            }

            // Get current rules for the guild
            // IMPORTANT: this GuildRules could be stale, so do not assume its current rules text
            // is updated

            GuildRules cachedRules = GuildRulesRepository.getInstance().getGuildRulesFromCache(guildId);
            ChannelID rulesChannelID = cachedRules != null ? cachedRules.rulesChannelId() : null;

            if (rulesChannelID == null) {
                GuildPreferences latestPreferences = GuildPreferencesRepository.getInstance().getGuildPreferences(guildId);
                rulesChannelID = latestPreferences != null ? latestPreferences.rulesChannelID() : null;
            }

            if (rulesChannelID == null) {
                logger.debug("Rules channel missing for guild {} ({}), attempting onboarding backfill", guild.getName(), guildId.value());
                boolean success = Onboarding.getInstance().setupGuild(guild);
                if (!success) {
                    logger.warn("Onboarding backfill failed for guild {} ({})", guild.getName(), guildId.value());
                } else {
                    GuildPreferences latestPreferences = GuildPreferencesRepository.getInstance().getGuildPreferences(guildId);
                    rulesChannelID = latestPreferences != null ? latestPreferences.rulesChannelID() : null;
                }
            }

            if (rulesChannelID == null) {
                logger.debug("No rules channel configured for guild: {} ({}), storing unconfigured state", guild.getName(), guildId.value());
                boolean success = GuildRulesRepository.getInstance()
                    .addOrReplaceGuildRulesToDatabase(new GuildRules(guildId, null, null));
                if (!success) {
                    logger.warn("Failed to persist unconfigured rules state for guild: {} ({})", guild.getName(), guildId.value());
                    return UpdateOutcome.FAILED;
                }
                return UpdateOutcome.SKIPPED;
            }

            String updatedRules = getGuildRulesFromDiscord(guild, rulesChannelID);

            if (updatedRules == null || updatedRules.isBlank()) {
                logger.debug("No rules found for guild: {} ({}).", guild.getName(), guildId.value());
                return UpdateOutcome.SKIPPED;
            }

            GuildRules currentGuildRules = new GuildRules(guildId, rulesChannelID, updatedRules);

            boolean success = GuildRulesRepository.getInstance().addOrReplaceGuildRulesToDatabase(currentGuildRules);

            if (success) {
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


    @Nullable
    private String getGuildRulesFromDiscord(Guild guild, ChannelID rulesChannelId) {
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
            logger.warn("Failed to fetch rules for guild {}", guild.getId(), e);
            return null;
        }
    }

    @Nullable
    private String extractRuleText(Message message) {
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
