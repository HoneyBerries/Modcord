package net.honeyberries.datatypes.action;

import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.discord.UserID;
import org.jetbrains.annotations.NotNull;

import java.time.Instant;
import java.util.UUID;

public record AppealData(
        @NotNull UUID id,
        @NotNull Instant submittedTimestamp,
        @NotNull GuildID guildID,
        @NotNull UserID userId,
        @NotNull String reason,
        @NotNull ActionData actionData
) {
}
