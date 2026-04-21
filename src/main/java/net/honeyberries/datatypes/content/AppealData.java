package net.honeyberries.datatypes.content;

import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.discord.UserID;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;

import java.util.UUID;

public record AppealData(
        @NotNull UUID id,
        @NotNull GuildID guildID,
        @NotNull UserID userId,
        @NotNull String reason,
        @Nullable UUID actionId,
        boolean isOpen
) {
}
