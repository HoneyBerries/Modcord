package net.honeyberries.services;

import net.honeyberries.config.AppConfig;
import net.honeyberries.datatypes.content.ModerationMessage;
import net.honeyberries.datatypes.discord.MessageID;

import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.*;

public class GuildMessageMap extends HashMap<MessageID, ModerationMessage> {

    private final Map<MessageID, OffsetDateTime> messageQueueTimes = new HashMap<>();

    public void addMessage(ModerationMessage message) {
        put(message.messageId(), message);
        messageQueueTimes.put(message.messageId(), OffsetDateTime.now());
    }

    public ModerationMessage getMessage(MessageID messageId) {
        return get(messageId);
    }

    public void removeMessage(MessageID messageId) {
        remove(messageId);
        messageQueueTimes.remove(messageId);
    }

    public void replaceMessage(MessageID messageId, ModerationMessage message) {
        put(messageId, message);
        messageQueueTimes.putIfAbsent(messageId, OffsetDateTime.now());
    }

    public boolean containsMessage(MessageID messageId) {
        return containsKey(messageId);
    }

    /** Returns messages whose queue arrival time falls within [from, to). */
    private List<ModerationMessage> getMessagesBetween(OffsetDateTime from, OffsetDateTime to) {
        return this.values().stream()
                .filter(msg -> {
                    OffsetDateTime t = arrivalTime(msg);
                    return !t.isBefore(from) && (to == null || t.isBefore(to));
                })
                .sorted(Comparator.comparing(this::arrivalTime))
                .toList();
    }

    private OffsetDateTime arrivalTime(ModerationMessage msg) {
        return messageQueueTimes.getOrDefault(msg.messageId(), OffsetDateTime.now());
    }

    private static Duration secondsToDuration(double seconds) {
        return Duration.ofMillis(Math.round(seconds * 1000));
    }



    /** Fresh messages in [now - queueDuration, now]. */
    public List<ModerationMessage> getCurrentMessages() {
        OffsetDateTime cutoff = OffsetDateTime.now().minus(
                secondsToDuration(AppConfig.getInstance().getModerationQueueDuration()));
        return getMessagesBetween(cutoff, null);
    }

    /** Background context messages in [now - maxAge, now - queueDuration]. */
    public List<ModerationMessage> getHistoryContextMessages() {
        OffsetDateTime now = OffsetDateTime.now();
        OffsetDateTime from = now.minus(secondsToDuration(AppConfig.getInstance().getHistoryContextMaxAge()));
        OffsetDateTime to   = now.minus(secondsToDuration(AppConfig.getInstance().getModerationQueueDuration()));
        return getMessagesBetween(from, to);
    }

    /** History context + current messages combined, in chronological order. */
    public List<ModerationMessage> getAllMessagesForProcessing() {
        List<ModerationMessage> all = new ArrayList<>();
        all.addAll(getHistoryContextMessages());
        all.addAll(getCurrentMessages());
        return all;
    }

    public void clearQueue() {
        this.clear();
        messageQueueTimes.clear();
    }
}