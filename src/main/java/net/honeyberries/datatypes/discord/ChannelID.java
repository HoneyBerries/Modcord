package net.honeyberries.datatypes.discord;

import net.dv8tion.jda.api.entities.channel.Channel;
import net.dv8tion.jda.api.entities.channel.middleman.MessageChannel;
import net.honeyberries.discord.JDAManager;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;

import java.util.Objects;

/**
 * Strongly typed wrapper around a Discord message channel snowflake.
 * Provides helpers for constructing identifiers from JDA entities while keeping string/long conversions localized.
 * Using a dedicated type prevents mixing channel identifiers with other snowflakes elsewhere in the system.
 */
public record ChannelID(long value) {

    /**
     * Creates a {@code ChannelID} from a JDA {@link MessageChannel} instance.
     *
     * @param channel JDA channel whose id will be captured; must not be {@code null}
     * @return immutable identifier for the provided channel
     * @throws NullPointerException if {@code channel} is {@code null}
     */
    @NotNull
    public static ChannelID fromChannel(@NotNull MessageChannel channel) {
        Objects.requireNonNull(channel, "channel must not be null");
        return new ChannelID(channel.getIdLong());
    }

    /**
     * Parses an unsigned long snowflake string into a {@code ChannelID}.
     *
     * @param string channel snowflake as text; must not be {@code null}
     * @throws NumberFormatException if the string cannot be parsed as an unsigned long
     * @throws NullPointerException  if {@code string} is {@code null}
     */
    public ChannelID(@NotNull String string) {
        Objects.requireNonNull(string, "string must not be null");
        long id = Long.parseLong(string);
        this(id);
    }


    /**
     * Resolves the current {@code ChannelID} to its corresponding Discord channel in JDA.
     *
     * @return the {@link Channel} associated with the stored identifier, or {@code null} if no such channel exists
     */
    @Nullable
    public Channel toChannel() {
        return JDAManager.getInstance().getJDA().getGuildChannelById(value);
    }


    /**
     * Returns the snowflake identifier rendered as an unsigned decimal string.
     *
     * @return unsigned decimal representation of the channel id
     */
    @NotNull
    @Override
    public String toString() {
        return Long.toUnsignedString(value);
    }
}
