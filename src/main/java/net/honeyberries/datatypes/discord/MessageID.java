package net.honeyberries.datatypes.discord;

import net.dv8tion.jda.api.entities.Message;
import org.jetbrains.annotations.NotNull;

import java.util.Objects;

/**
 * Strongly typed wrapper around a Discord message snowflake.
 * Prevents accidental mixing of message identifiers with other ids and centralizes conversion helpers.
 */
public record MessageID(long value) {

    /**
     * Creates a {@code MessageID} from a JDA {@link Message}.
     *
     * @param message message whose id should be wrapped; must not be {@code null}
     * @return identifier bound to the provided message
     * @throws NullPointerException if {@code message} is {@code null}
     */
    @NotNull
    public static MessageID fromMessage(@NotNull Message message) {
        Objects.requireNonNull(message, "message must not be null");
        return new MessageID(message.getIdLong());
    }

    /**
     * Parses an unsigned snowflake string into a {@code MessageID}.
     *
     * @param string message snowflake as text; must not be {@code null}
     * @throws NumberFormatException if the string cannot be parsed
     * @throws NullPointerException  if {@code string} is {@code null}
     */
    public MessageID(@NotNull String string) {
        Objects.requireNonNull(string, "string must not be null");
        long id = Long.parseLong(string);
        this(id);
    }

    /**
     * Returns the snowflake identifier rendered as an unsigned decimal string.
     *
     * @return unsigned decimal representation of the message id
     */
    @NotNull
    @Override
    public String toString() {
        return Long.toUnsignedString(value);
    }
}

