package net.honeyberries.task;

import net.dv8tion.jda.api.JDA;
import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.Message;
import net.dv8tion.jda.api.entities.channel.Channel;
import net.dv8tion.jda.api.entities.channel.concrete.TextChannel;
import net.honeyberries.database.GuildRulesRepository;
import net.honeyberries.datatypes.content.GuildRules;
import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.message.EmbedParser;
import net.honeyberries.util.JDAManager;
import org.jetbrains.annotations.Nullable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.List;
import java.util.Objects;
import java.util.concurrent.ExecutionException;
import java.util.stream.Collectors;

/**
 * Task that periodically updates guild rules text for all guilds the bot is in.
 * This task goes through each guild and updates the rules_text while preserving
 * the rules_channel_id set by users.
 */
public class GuildRulesTask implements Runnable {

    private final Logger logger = LoggerFactory.getLogger(GuildRulesTask.class);
    private final JDA jda = JDAManager.getInstance().getJDA();

    /**
     * Runs this operation.
     */
    @Override
    public void run() {
        logger.info("GuildRulesTask started");

        try {
            // Collect all results from updateGuildRules for each guild
            List<Boolean> results = jda.getGuilds().parallelStream()
                .map(this::updateGuildRules)
                .toList();

            // Check if all operations succeeded
            boolean allSuccessful = results.stream().allMatch(Boolean::booleanValue);

            if (allSuccessful) {
                logger.debug("GuildRulesTask completed successfully for all {} guilds", results.size());

            } else {
                long failedCount = results.stream().filter(success -> !success).count();
                logger.warn("GuildRulesTask completed with {} failures out of {} guilds",
                        failedCount, results.size());
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
    private boolean updateGuildRules(Guild guild) {
        try {
            GuildID guildId = GuildID.fromGuild(guild);

            // Get current rules for the guild
            // IMPORTANT: this GuildRules could be stale, so do not assume its current rules text
            // is updated

            ChannelID rulesChannelID = Objects.requireNonNull(GuildRulesRepository.getInstance()
                    .getGuildRulesFromCache(guildId)).rulesChannelId();

            String updatedRules = getGuildRulesFromDiscord(guild, rulesChannelID);

            if (updatedRules == null || updatedRules.isBlank()) {
                logger.debug("No rules found for guild: {} ({}).", guild.getName(), guildId.value());
                return false;
            }

            GuildRules currentGuildRules = new GuildRules(guildId, rulesChannelID, updatedRules);

            boolean success = GuildRulesRepository.getInstance().addOrReplaceGuildRulesToDatabase(currentGuildRules);

            if (success) {
                logger.debug("Updated rules for guild: {} ({})", guild.getName(), guildId.value());
            } else {
                logger.warn("Failed to update rules for guild: {} ({})", guild.getName(), guildId.value());
            }
            return success;

        } catch (Exception e) {
            logger.error("Error updating rules for guild {}", guild.getId(), e);
            return false;
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
                    .map(EmbedParser::parseEmbed)
                    .filter(s -> !s.isBlank())
                    .collect(Collectors.joining("\n\n"));

        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            logger.warn("Interrupted while fetching rules for guild {}", guild.getId());
            return "";
        } catch (ExecutionException e) {
            logger.warn("Failed to fetch rules for guild {}", guild.getId(), e);
            return "";
        }
    }


}
