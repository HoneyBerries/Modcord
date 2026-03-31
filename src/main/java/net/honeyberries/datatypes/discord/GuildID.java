package net.honeyberries.datatypes.discord;

import net.dv8tion.jda.api.entities.Guild;
import org.jetbrains.annotations.NotNull;

import java.util.Objects;

/**
 * Strongly typed wrapper for a Discord guild snowflake.
 * Keeps guild identifiers distinct from other ids and concentrates conversion logic in one place.
 */
public record GuildID(long value) {

    /**
     * Creates a {@code GuildID} from a JDA {@link Guild}.
     *
     * @param guild guild entity providing the id; must not be {@code null}
     * @return identifier corresponding to the provided guild
     * @throws NullPointerException if {@code guild} is {@code null}
     */
    @NotNull
    public static GuildID fromGuild(@NotNull Guild guild) {
        Objects.requireNonNull(guild, "guild must not be null");
        return new GuildID(guild.getIdLong());
    }

    /**
     * Parses an unsigned snowflake string into a {@code GuildID}.
     *
     * @param string guild snowflake as text; must not be {@code null}
     * @throws NumberFormatException if the string cannot be parsed
     * @throws NullPointerException  if {@code string} is {@code null}
     */
    public GuildID(@NotNull String string) {
        Objects.requireNonNull(string, "string must not be null");
        long id = Long.parseLong(string);
        this(id);
    }

    /**
     * Returns the snowflake identifier rendered as an unsigned decimal string.
     *
     * @return unsigned decimal representation of the guild id
     */
    @NotNull
    @Override
    public String toString() {
        return Long.toUnsignedString(value);
    }
}

