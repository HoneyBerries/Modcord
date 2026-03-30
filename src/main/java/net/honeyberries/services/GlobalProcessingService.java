package net.honeyberries.services;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.openai.models.ResponseFormatJsonSchema;
import com.openai.models.chat.completions.ChatCompletionMessageParam;
import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.Member;
import net.dv8tion.jda.api.entities.Message;
import net.dv8tion.jda.api.entities.channel.Channel;
import net.honeyberries.ai.*;
import net.honeyberries.datatypes.action.ActionData;
import net.honeyberries.datatypes.content.GuildModerationBatch;
import net.honeyberries.datatypes.content.ModerationMessage;
import net.honeyberries.datatypes.content.ModerationUser;
import net.honeyberries.datatypes.content.ModerationUserChannel;
import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.discord.MessageID;
import net.honeyberries.datatypes.discord.UserID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.*;
import java.util.concurrent.ExecutionException;
import java.util.stream.Collectors;

public class GlobalProcessingService {

    private final Logger logger = LoggerFactory.getLogger(GlobalProcessingService.class);

    private static final GlobalProcessingService INSTANCE = new GlobalProcessingService();
    private final Map<GuildID, GuildMessageMap> guildQueues;

    private GlobalProcessingService() {
        this.guildQueues = new HashMap<>();
    }

    public static GlobalProcessingService getInstance() {
        return INSTANCE;
    }

    public void addMessage(Guild guild, Message message, boolean isHistory) {
        GuildID guildId = GuildID.fromGuild(guild);

        ModerationMessage moderationMessage = ModerationMessage.fromMessage(message, isHistory);

        guildQueues.computeIfAbsent(guildId, id -> new GuildMessageMap()).addMessage(moderationMessage);
        logger.debug("Added message {} to guild {}", moderationMessage.messageId(), guildId);

    }

    public void updateMessage(Guild guild, Message message, boolean isHistory) {
        GuildID guildId = GuildID.fromGuild(guild);

        ModerationMessage moderationMessage = ModerationMessage.fromMessage(message, isHistory);
        MessageID messageId = moderationMessage.messageId();

        guildQueues.computeIfAbsent(guildId,
                id -> new GuildMessageMap()).replaceMessage(messageId, moderationMessage);

        logger.debug("Updated message {} in guild {}", messageId, guildId);
    }


    public void removeMessage(Guild guild, MessageID messageID) {
        GuildID guildId = GuildID.fromGuild(guild);
        guildQueues.computeIfAbsent(guildId, id -> new GuildMessageMap()).removeMessage(messageID);
        logger.debug("Removed message {} from guild {}", messageID, guildId);
    }


    public List<ActionData> getActionDataFromAI(GuildMessageMap guildMessageMap, Guild guild) {
        GuildID guildId = GuildID.fromGuild(guild);

        List<ModerationUser> users = buildModerationUsers(guildMessageMap.getCurrentMessages(), guild);
        List<ModerationUser> historyUsers = buildModerationUsers(guildMessageMap.getHistoryContextMessages(), guild);

        GuildModerationBatch batch = new GuildModerationBatch(
                guildId,
                guild.getName(),
                Map.of(),
                users,
                historyUsers
        );

        ChatCompletionMessageParam inputs;
        ChatCompletionMessageParam systemPrompt;
        ResponseFormatJsonSchema schema;
        String response;

        try {
            inputs = GuildModerationBatchToAIInput.createMessageFromGuildModerationBatch(batch);
        } catch (GuildModerationBatchToAIInput.GuildModerationBatchSerializationException e) {
            logger.error("Failed to serialize guild moderation batch for guild {}", guildId, e);
            return List.of();
        }

        try {
            schema = DynamicSchemaGenerator.getInstance().createDynamicOutputSchema(batch);
        } catch (DynamicSchemaGenerator.DynamicSchemaGeneratorParseException e) {
            logger.error("Failed to generate dynamic schema for guild {}", guildId, e);
            return List.of();
        }

        try {
            systemPrompt = DynamicSystemPrompt.getInstance().createDynamicSystemPrompt(guildId);
        } catch (Exception e) {
            logger.error("Failed to generate dynamic system prompt for guild {}", guildId, e);
            return List.of();
        }

        try {
            response = InferenceEngine.getInstance().generateResponse(List.of(systemPrompt, inputs), schema).get();
        } catch (ExecutionException | InterruptedException e) {
            logger.error("Failed to generate response for guild {}", guildId, e);
            return List.of();
        }

        List<ActionData> actionDataList;

        try {
            actionDataList = ActionDataJSONParser.getInstance().parse(response, guildId);
        } catch (JsonProcessingException e) {
            logger.error("Failed to parse AI response for guild {}", guildId, e);
            return List.of();
        }

        return actionDataList;
    }

    private List<ModerationUser> buildModerationUsers(List<ModerationMessage> messages, Guild guild) {
        Map<UserID, Map<ChannelID, List<ModerationMessage>>> userChannelMap = new HashMap<>();
        for (ModerationMessage msg : messages) {
            userChannelMap
                    .computeIfAbsent(msg.userId(), k -> new HashMap<>())
                    .computeIfAbsent(msg.channelId(), k -> new ArrayList<>())
                    .add(msg);
        }

        List<ModerationUser> result = new ArrayList<>();
        for (Map.Entry<UserID, Map<ChannelID, List<ModerationMessage>>> userEntry : userChannelMap.entrySet()) {
            UserID userId = userEntry.getKey();

            Member member = guild.getMemberById(userId.value());
            if (member == null) continue;

            List<ModerationUserChannel> channels = new ArrayList<>();
            for (Map.Entry<ChannelID, List<ModerationMessage>> channelEntry : userEntry.getValue().entrySet()) {
                ChannelID channelId = channelEntry.getKey();
                Channel channel = guild.getGuildChannelById(channelId.value());
                String channelName = channel != null ? channel.getName() : "Unknown";
                channels.add(new ModerationUserChannel(userId, channelId, channelName, channelEntry.getValue()));
            }

            List<String> roles = member.getRoles().stream()
                    .map(net.dv8tion.jda.api.entities.Role::getName)
                    .collect(Collectors.toList());

            result.add(new ModerationUser(
                    userId,
                    new net.honeyberries.datatypes.discord.DiscordUsername(userId, member.getEffectiveName()),
                    member.getTimeJoined().toLocalDateTime(),
                    member,
                    guild,
                    roles,
                    channels
            ));
        }
        return result;
    }


    public boolean processActions(List<ActionData> actions) {
        //TODO: Implement the actual processing of actions, including applying them to the guild and handling any errors.
        return false;
    }


}
