package net.honeyberries.datatypes.discord;

import net.dv8tion.jda.api.entities.Guild;
import org.jetbrains.annotations.NotNull;

public record GuildID(long value) {
    public static GuildID fromGuild(Guild guild) {
        return new GuildID(guild.getIdLong());
    }

    public GuildID(String string) {
        long id = Long.parseLong(string);
        this(id);
    }

    @NotNull
    @Override
    public String toString() {
        return Long.toUnsignedString(value);
    }
}


