package net.honeyberries.task;

import net.dv8tion.jda.api.JDA;
import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.channel.concrete.TextChannel;
import net.honeyberries.database.repository.ChannelGuidelinesRepository;
import net.honeyberries.database.Database;
import net.honeyberries.database.repository.GuildPreferencesRepository;
import net.honeyberries.datatypes.content.ChannelGuidelines;
import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.preferences.GuildPreferences;
import net.honeyberries.discord.JDAManager;
import net.honeyberries.preferences.Onboarding;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.List;

/**
 * The {@code ChannelGuidelinesTask} class is responsible for updating and persisting
 * the guidelines of text channels across all guilds in a Discord bot environment.
 * It implements the {@code Runnable} interface to allow execution in a concurrent context.
 * <p>
 * This task performs the following steps during execution:
 * - Verifies the health of the database before starting the operation.
 * - Iterates through all guilds and their respective text channels to extract and save
 *   channel guidelines.
 * - Logs the result of the operation, including the counts of updated, skipped, and
 *   failed channels.
 * <p>
 * The class ensures that guild entries exist in the database before updating the
 * channel guidelines to prevent database integrity violations.
 * <p>
 * Error handling is incorporated to log any issues encountered during execution.
 */
public class ChannelGuidelinesTask implements Runnable {

    private enum UpdateOutcome {
        UPDATED,
        SKIPPED,
        FAILED
    }

    private final Logger logger = LoggerFactory.getLogger(ChannelGuidelinesTask.class);

    @Override
    public void run() {
        logger.info("ChannelGuidelinesTask started");

        if (!Database.getInstance().isHealthy()) {
            logger.warn("Skipping ChannelGuidelinesTask because database is unavailable");
            return;
        }

        JDA jda = JDAManager.getInstance().getJDA();

        try {
            List<UpdateOutcome> results = jda.getGuilds().parallelStream()
                    .flatMap(guild -> guild.getTextChannels().parallelStream()
                            .map(channel -> updateChannelGuidelines(guild, channel)))
                    .toList();

            long updatedCount = results.stream().filter(outcome -> outcome == UpdateOutcome.UPDATED).count();
            long skippedCount = results.stream().filter(outcome -> outcome == UpdateOutcome.SKIPPED).count();
            long failedCount = results.stream().filter(outcome -> outcome == UpdateOutcome.FAILED).count();

            if (failedCount > 0) {
                logger.warn("ChannelGuidelinesTask completed with {} updated, {} skipped, {} failed out of {} channels",
                        updatedCount, skippedCount, failedCount, results.size());
            } else {
                logger.info("ChannelGuidelinesTask completed with {} updated and {} skipped out of {} channels",
                        updatedCount, skippedCount, results.size());
            }
        } catch (Exception e) {
            logger.error("Error in ChannelGuidelinesTask", e);
        }
    }


    /**
     * Updates the guidelines for a specific text channel within a guild.
     * This operation ensures that the guild is properly onboarded in the system
     * before persisting guidelines information for the specified channel.
     * Exceptions are handled internally, and the operation's outcome is returned.
     *
     * @param guild   the guild containing the channel; must not be null
     * @param channel the text channel whose guidelines are being updated; must not be null
     * @return an {@code UpdateOutcome} indicating the result of the operation:
     *         {@code UPDATED} if the guidelines were successfully stored,
     *         {@code SKIPPED} if no guidelines were configured,
     *         or {@code FAILED} if the update process encountered an error
     */
    private UpdateOutcome updateChannelGuidelines(@NotNull Guild guild, @NotNull TextChannel channel) {
        try {
            GuildID guildId = GuildID.fromGuild(guild);
            ChannelID channelId = new ChannelID(channel.getIdLong());

            // Ensure guild exists in guild_preferences table before inserting channel guidelines
            // This prevents foreign key constraint violations
            if (!ensureGuildExists(guildId, guild)) {
                return UpdateOutcome.FAILED;
            }

            // Extract and persist guidelines
            String guidelinesText = getChannelGuidelinesText(channel);
            return persistChannelGuidelines(guildId, channelId, channel.getName(), guidelinesText);

        } catch (Exception e) {
            logger.error("Error updating guidelines for channel {}", channel.getId(), e);
            return UpdateOutcome.FAILED;
        }
    }

    /**
     * Ensures that the specified guild exists in the system by verifying its presence
     * in the database or initializing it with default preferences if absent.
     *
     * @param guildId the identifier of the guild to check; must not be null
     * @param guild   the guild entity to onboard if it does not already exist; must not be null
     * @return {@code true} if the guild already exists or was successfully onboarded, {@code false} otherwise
     */
    private boolean ensureGuildExists(@NotNull GuildID guildId, @NotNull Guild guild) {
        GuildPreferences existing = GuildPreferencesRepository.getInstance().getGuildPreferences(guildId);
        if (existing != null) {
            return true;
        }

        logger.debug("Guild {} not found in database, onboarding guild with default preferences", guildId.value());
        boolean success = Onboarding.getInstance().setupGuild(guild);
        if (!success) {
            logger.error("Failed to onboard guild {}", guildId.value());
        }
        return success;
    }

    /**
     * Persists the guidelines information for a specific channel in a guild.
     * If guidelines are provided, they are stored in the database; otherwise, the channel is marked as unconfigured.
     *
     * @param guildId        the identifier of the guild that owns the channel; must not be null
     * @param channelId      the identifier of the channel whose guidelines are being persisted; must not be null
     * @param channelName    the name of the channel; must not be null
     * @param guidelinesText the text of the guidelines for the channel; may be null or empty if no guidelines are configured
     * @return an {@code UpdateOutcome} indicating the result of the operation:
     *         {@code UPDATED} if new guidelines were successfully stored,
     *         {@code SKIPPED} if no guidelines were configured,
     *         or {@code FAILED} if the persistence operation was unsuccessful
     */
    private UpdateOutcome persistChannelGuidelines(@NotNull GuildID guildId, @NotNull ChannelID channelId, @NotNull String channelName, @Nullable String guidelinesText) {
        boolean hasGuidelines = guidelinesText != null && !guidelinesText.isBlank();

        if (!hasGuidelines) {
            logger.debug("No channel topic configured for channel: {} in guild: {}, storing unconfigured state",
                    channelName, guildId.value());
        }

        ChannelGuidelines guidelines = new ChannelGuidelines(guildId, channelId, hasGuidelines ? guidelinesText : null);
        boolean success = ChannelGuidelinesRepository.getInstance().addOrReplaceChannelGuidelinesToDatabase(guidelines);

        if (!success) {
            logger.warn("Failed to persist {} guidelines state for channel: {} ({})",
                    hasGuidelines ? "updated" : "unconfigured", channelName, channelId.value());
            return UpdateOutcome.FAILED;
        }

        if (hasGuidelines) {
            logger.debug("Updated guidelines for channel: {} ({})", channelName, channelId.value());
            return UpdateOutcome.UPDATED;
        } else {
            return UpdateOutcome.SKIPPED;
        }
    }

    /**
     * Retrieves the guidelines text set in the topic of the specified text channel.
     *
     * @param channel the text channel from which to retrieve the guidelines text. Must not be null.
     * @return the topic of the specified text channel if present, otherwise null.
     */
    @Nullable
    private String getChannelGuidelinesText(@NotNull TextChannel channel) {
        return channel.getTopic();
    }

}