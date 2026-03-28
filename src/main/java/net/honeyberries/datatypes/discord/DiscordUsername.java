package net.honeyberries.datatypes.discord;

import net.dv8tion.jda.api.entities.User;

public record DiscordUsername(UserID userId, String username) {
    public static DiscordUsername fromUser(User user) {
        return new DiscordUsername(new UserID(user.getIdLong()), user.getName());
    }
}

