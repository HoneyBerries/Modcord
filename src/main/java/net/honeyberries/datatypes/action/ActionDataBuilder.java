package net.honeyberries.datatypes.action;

import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.discord.UserID;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

public class ActionDataBuilder {
    private final UUID id;
    private final GuildID guildId;
    private final UserID userId;
    private final ActionType action;
    private final String reason;
    private final long timeoutDuration;
    private final long banDuration;
    private final List<MessageDeletion> messageDeletions = new ArrayList<>();

    public ActionDataBuilder(
            UUID id,
            GuildID guildId,
            UserID userId,
            ActionType action,
            String reason,
            long timeoutDuration,
            long banDuration
    ) {
        this.id = id;
        this.guildId = guildId;
        this.userId = userId;
        this.action = action;
        this.reason = reason;
        this.timeoutDuration = timeoutDuration;
        this.banDuration = banDuration;
    }

    public void addMessageDeletion(MessageDeletion deletion) {
        messageDeletions.add(deletion);
    }

    public ActionData build() {
        return new ActionData(
                id,
                guildId,
                userId,
                action,
                reason,
                timeoutDuration,
                banDuration,
                messageDeletions
        );
    }
}