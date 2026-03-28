package net.honeyberries.datatypes.discord;

import net.dv8tion.jda.api.entities.Message;
import org.jetbrains.annotations.NotNull;

public record MessageID(long value) {
    public static MessageID fromMessage(Message message) {
        return new MessageID(message.getIdLong());
    }


    public MessageID(String string) {
        long id = Long.parseLong(string);
        this(id);
    }

    @NotNull
    @Override
    public String toString() {
        return Long.toUnsignedString(value);
    }
}


