package net.honeyberries.datatypes.discord;

import net.dv8tion.jda.api.entities.channel.middleman.MessageChannel;
import org.jetbrains.annotations.NotNull;

public record ChannelID(long value) {
    public static ChannelID fromChannel(MessageChannel channel) {
        return new ChannelID(channel.getIdLong());
    }

    public ChannelID(String string) {
        long id = Long.parseLong(string);
        this(id);
    }


    @NotNull
    @Override
    public String toString() {
        return Long.toUnsignedString(value);
    }
}


