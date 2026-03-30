package net.honeyberries.task;

import net.dv8tion.jda.api.JDA;
import net.dv8tion.jda.api.entities.Guild;
import net.honeyberries.database.GuildRulesRepository;
import net.honeyberries.datatypes.content.GuildRules;
import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.util.JDAManager;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Task that periodically updates guild rules text for all guilds the bot is in.
 * This task goes through each guild and updates the rules_text while preserving
 * the rules_channel_id set by users.
 */
public class GuildRulesTask implements Runnable {
    
    private static final Logger logger = LoggerFactory.getLogger(GuildRulesTask.class);
    private final GuildRulesRepository rulesRepository = GuildRulesRepository.getInstance();

    /**
     * Runs this operation.
     */
    @Override
    public void run() {
        logger.info("GuildRulesTask started");

        try {
            JDA jda = JDAManager.getInstance().getJDA();
            if (jda == null) {
                logger.warn("JDA instance not available, skipping GuildRulesTask");
                return;
            }

            // Iterate through all guilds the bot is in
            for (Guild guild : jda.getGuilds()) {
                updateGuildRules(guild);
            }

            logger.debug("GuildRulesTask completed successfully");
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
    private void updateGuildRules(Guild guild) {
        try {
            GuildID guildId = GuildID.fromGuild(guild);
            
            // Get current rules for the guild
            String rulesText =
            GuildRules currentRules = ;
            
            if (currentRules == null) {
                logger.debug("No rules configured for guild: {} ({})", guild.getName(), guildId.value());
                return;
            }


            String updatedRulesText = currentRules.rulesText();
            
            // Update only the rules text, preserving the channel ID
            boolean success = rulesRepository.updateGuildRulesTextOnly(guildId, updatedRulesText);
            
            if (success) {
                logger.debug("Updated rules for guild: {} ({})", guild.getName(), guildId.value());
            } else {
                logger.warn("Failed to update rules for guild: {} ({})", guild.getName(), guildId.value());
            }
        } catch (Exception e) {
            logger.error("Error updating rules for guild {}", guild.getId(), e);
        }
    }

    private void getGuildRulesFromDiscord(Guild guild, ChannelID rulesChannelId) {
        // TODO: This method would contain logic to fetch the rules text from the specified channel in Discord.
        // TODO: For example, it could fetch the latest message from the channel and use its content as the rules text.
        // TODO: This is a placeholder for the actual implementation.
    }}


}
