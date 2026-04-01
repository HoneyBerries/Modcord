package net.honeyberries.task;

import net.dv8tion.jda.api.JDA;
import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.channel.concrete.TextChannel;
import net.honeyberries.database.ChannelGuidelinesRepository;
import net.honeyberries.database.GuildPreferencesRepository;
import net.honeyberries.datatypes.content.ChannelGuidelines;
import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.preferences.GuildPreferences;
import net.honeyberries.discord.JDAManager;
import org.jetbrains.annotations.Nullable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.List;

/**
 * Task that periodically updates channel guidelines for all channels in all guilds.
 * This task extracts the channel topic and stores it as guidelines in the database.
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

    private UpdateOutcome updateChannelGuidelines(Guild guild, TextChannel channel) {
        try {
            GuildID guildId = GuildID.fromGuild(guild);
            ChannelID channelId = new ChannelID(channel.getIdLong());

            // Ensure guild exists in guild_preferences table before inserting channel guidelines
            // This prevents foreign key constraint violations
            GuildPreferences existingPreferences = GuildPreferencesRepository.getInstance()
                .getGuildPreferences(guildId);
            
            if (existingPreferences == null) {
                logger.debug("Guild {} not found in database, creating default preferences", guildId.value());
                GuildPreferences defaultPreferences = new GuildPreferences(guildId);
                boolean preferencesCreated = GuildPreferencesRepository.getInstance()
                    .addOrUpdateGuildPreferences(defaultPreferences);
                
                if (!preferencesCreated) {
                    logger.warn("Failed to create guild preferences for guild: {}, skipping channel guidelines", guildId.value());
                    return UpdateOutcome.FAILED;
                }
            }

            String updatedGuidelinesText = getChannelGuidelinesText(channel);

            if (updatedGuidelinesText == null || updatedGuidelinesText.isBlank()) {
                logger.debug("No channel topic configured for channel: {} in guild: {}, storing unconfigured state",
                    channel.getName(), guildId.value());
                ChannelGuidelines unconfiguredGuidelines = new ChannelGuidelines(guildId, channelId, null);
                boolean success = ChannelGuidelinesRepository.getInstance()
                    .addOrReplaceChannelGuidelinesToDatabase(unconfiguredGuidelines);
                if (!success) {
                    logger.warn("Failed to persist unconfigured guidelines state for channel: {} ({})", channel.getName(), channelId.value());
                    return UpdateOutcome.FAILED;
                }
                return UpdateOutcome.SKIPPED;
            }

            ChannelGuidelines updatedGuidelines = new ChannelGuidelines(guildId, channelId, updatedGuidelinesText);
            boolean success = ChannelGuidelinesRepository.getInstance()
                .addOrReplaceChannelGuidelinesToDatabase(updatedGuidelines);

            if (success) {
                logger.debug("Updated guidelines for channel: {} ({})", channel.getName(), channelId.value());
                return UpdateOutcome.UPDATED;
            } else {
                logger.warn("Failed to update guidelines for channel: {} ({})", channel.getName(), channelId.value());
                return UpdateOutcome.FAILED;
            }

        } catch (Exception e) {
            logger.error("Error updating guidelines for channel {}", channel.getId(), e);
            return UpdateOutcome.FAILED;
        }
    }

    @Nullable
    private String getChannelGuidelinesText(TextChannel channel) {
        return channel.getTopic();
    }


}
