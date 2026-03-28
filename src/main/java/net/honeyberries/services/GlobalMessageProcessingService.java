package net.honeyberries.services;

import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.Message;
import net.honeyberries.datatypes.action.ActionData;
import net.honeyberries.datatypes.content.ModerationMessage;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.discord.MessageID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class GlobalMessageProcessingService {

    private final Logger logger = LoggerFactory.getLogger(GlobalMessageProcessingService.class);

    private static final GlobalMessageProcessingService INSTANCE = new GlobalMessageProcessingService();
    private final Map<GuildID, GuildMessageMap> guildQueues;

    private GlobalMessageProcessingService() {
        this.guildQueues = new HashMap<>();
    }

    public static GlobalMessageProcessingService getInstance() {
        return INSTANCE;
    }

    public void addMessage(Guild guild, Message message, boolean isHistory) {
        GuildID guildId = GuildID.fromGuild(guild);

        ModerationMessage moderationMessage = ModerationMessage.fromMessage(message, isHistory);

        guildQueues.computeIfAbsent(guildId, id -> new GuildMessageMap()).addMessage(moderationMessage);
    }

    public void updateMessage(Guild guild, Message message, boolean isHistory) {
            GuildID guildId = GuildID.fromGuild(guild);

            ModerationMessage moderationMessage = ModerationMessage.fromMessage(message, isHistory);
            MessageID messageId = moderationMessage.messageId();

            guildQueues.computeIfAbsent(guildId,
                    id -> new GuildMessageMap()).replaceMessage(messageId, moderationMessage);

            logger.debug("Updated message {} in guild {}", messageId, guildId);
    }


    public List<ActionData> getActionDataFromAI(GuildMessageMap guildMessageMap) {
        //TODO: Implement the AI logic to generate action data based on the messages in the queue.
        return List.of();
    }


    public boolean processActions(List<ActionData> actions) {
        //TODO: Implement the actual processing of actions, including applying them to the guild and handling any errors.
        return false;
    }


}
