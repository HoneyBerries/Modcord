package net.honeyberries.datatypes.discord;

import net.dv8tion.jda.api.entities.User;
import org.jetbrains.annotations.NotNull;

public record UserID(long value) {
    public static UserID fromUser(User user) {
        return new UserID(user.getIdLong());
    }

    public UserID(String string) {
        long id = Long.parseLong(string);
        this(id);
    }

    @NotNull
    @Override
    public String toString() {
        return Long.toUnsignedString(value);
    }
}


