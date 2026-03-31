package net.honeyberries.services;

import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.Message;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.discord.MessageID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.HashMap;
import java.util.Map;

public class GlobalOrchestrationService {

    private final Logger logger = LoggerFactory.getLogger(GlobalOrchestrationService.class);

    private static final GlobalOrchestrationService INSTANCE = new GlobalOrchestrationService();
    private final Map<GuildID, GuildMessageProcessingService> guildServices = new HashMap<>();

    private GlobalOrchestrationService() {}

    public static GlobalOrchestrationService getInstance() {
        return INSTANCE;
    }

    public void addMessage(Guild guild, Message message, boolean isHistory) {
        getOrCreate(guild).addMessage(message, isHistory);
    }

    public void updateMessage(Guild guild, Message message, boolean isHistory) {
        getOrCreate(guild).updateMessage(message, isHistory);
    }

    public void removeMessage(Guild guild, MessageID messageId) {
        getOrCreate(guild).removeMessage(messageId);
    }

    public void processGuild(Guild guild) {
        logger.info("Triggering processing for guild {}", guild.getId());
        getOrCreate(guild).processAndApply();
    }

    private GuildMessageProcessingService getOrCreate(Guild guild) {
        return guildServices.computeIfAbsent(
                GuildID.fromGuild(guild),
                id -> new GuildMessageProcessingService(guild)
        );
    }
}