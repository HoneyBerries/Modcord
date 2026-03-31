package net.honeyberries.task;

import net.dv8tion.jda.api.JDA;
import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.channel.concrete.TextChannel;
import net.honeyberries.database.ChannelGuidelinesRepository;
import net.honeyberries.datatypes.content.ChannelGuidelines;
import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.util.JDAManager;
import org.jetbrains.annotations.Nullable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.List;

/**
 * Task that periodically updates channel guidelines for all channels in all guilds.
 * This task extracts the channel topic and stores it as guidelines in the database.
 */
public class ChannelGuidelinesTask implements Runnable {

    private final Logger logger = LoggerFactory.getLogger(ChannelGuidelinesTask.class);
    private final JDA jda = JDAManager.getInstance().getJDA();

    @Override
    public void run() {
        logger.info("ChannelGuidelinesTask started");

        try {
            List<Boolean> results = jda.getGuilds().parallelStream()
                .flatMap(guild -> guild.getTextChannels().parallelStream()
                    .map(channel -> updateChannelGuidelines(guild, channel)))
                .toList();

            boolean allSuccessful = results.stream().allMatch(Boolean::booleanValue);

            if (allSuccessful) {
                logger.debug("ChannelGuidelinesTask completed successfully for {} channels", results.size());
            } else {
                long failedCount = results.stream().filter(success -> !success).count();
                logger.warn("ChannelGuidelinesTask completed with {} failures out of {} channels",
                    failedCount, results.size());
            }
        } catch (Exception e) {
            logger.error("Error in ChannelGuidelinesTask", e);
        }
    }

    private boolean updateChannelGuidelines(Guild guild, TextChannel channel) {
        try {
            GuildID guildId = GuildID.fromGuild(guild);
            ChannelID channelId = new ChannelID(channel.getIdLong());

            String updatedGuidelinesText = getChannelGuidelinesText(channel);

            if (updatedGuidelinesText == null || updatedGuidelinesText.isBlank()) {
                logger.debug("No updatedGuidelines found for channel: {} in guild: {}", channel.getName(), guildId.value());
                return false;
            }

            ChannelGuidelines updatedGuidelines = new ChannelGuidelines(guildId, channelId, updatedGuidelinesText);
            boolean success = ChannelGuidelinesRepository.getInstance()
                .addOrReplaceChannelGuidelinesToDatabase(updatedGuidelines);

            if (success) {
                logger.debug("Updated updatedGuidelines for channel: {} ({})", channel.getName(), channelId.value());
            } else {
                logger.warn("Failed to update updatedGuidelines for channel: {} ({})", channel.getName(), channelId.value());
            }
            return success;

        } catch (Exception e) {
            logger.error("Error updating guidelines for channel {}", channel.getId(), e);
            return false;
        }
    }

    @Nullable
    private String getChannelGuidelinesText(TextChannel channel) {
        return channel.getTopic();
    }


}
