package net.honeyberries.datatypes.action;

import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.discord.UserID;

import java.util.List;
import java.util.UUID;

public record ActionData(
        UUID id, // 👈 IMPORTANT (you’ll want this later)
        GuildID guildId,
        UserID userId,
        ActionType action,
        String reason,
        long timeoutDuration,
        long banDuration,
        List<MessageDeletion> deletions
) {

    public ActionData(
            UUID id,
            GuildID guildId,
            UserID userId,
            ActionType action,
            String reason,
            long timeoutDuration,
            long banDuration
    ) {
        this(id, guildId, userId, action, reason, timeoutDuration, banDuration, List.of());
    }
}