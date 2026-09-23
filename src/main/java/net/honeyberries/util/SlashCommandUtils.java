package net.honeyberries.util;

import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.MessageEmbed;
import net.dv8tion.jda.api.events.interaction.command.SlashCommandInteractionEvent;
import net.dv8tion.jda.api.interactions.callbacks.IReplyCallback;
import net.dv8tion.jda.api.utils.messages.MessageCreateData;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;

import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;
import java.util.function.Function;

/**
 * Shared helpers for slash-command (and related component/modal) interaction handlers.
 *
 * <p>Centralizes patterns that were previously duplicated across the
 * {@code net.honeyberries.discord.slashCommands} package: ephemeral replies in their
 * various forms, guild-context validation, UUID option parsing, and sending a batch of
 * embeds as ephemeral follow-ups.
 */
public final class SlashCommandUtils {

    private SlashCommandUtils() {
        // Utility class; no instances.
    }

    /**
     * Sends an ephemeral text reply to an interaction.
     *
     * @param event   the interaction to reply to, must not be {@code null}
     * @param message the reply text, must not be {@code null}
     */
    public static void replyEphemeral(@NotNull IReplyCallback event, @NotNull String message) {
        Objects.requireNonNull(event, "event must not be null");
        Objects.requireNonNull(message, "message must not be null");
        event.reply(message).setEphemeral(true).queue();
    }

    /**
     * Sends an ephemeral embed reply to an interaction.
     *
     * @param event the interaction to reply to, must not be {@code null}
     * @param embed the embed to send, must not be {@code null}
     */
    public static void replyEphemeral(@NotNull IReplyCallback event, @NotNull MessageEmbed embed) {
        Objects.requireNonNull(event, "event must not be null");
        Objects.requireNonNull(embed, "embed must not be null");
        event.replyEmbeds(embed).setEphemeral(true).queue();
    }

    /**
     * Sends an ephemeral reply built from pre-assembled message data (e.g. an embed produced
     * by one of the {@code *EmbedUI} builders).
     *
     * @param event   the interaction to reply to, must not be {@code null}
     * @param message the message data to send, must not be {@code null}
     */
    public static void replyEphemeral(@NotNull IReplyCallback event, @NotNull MessageCreateData message) {
        Objects.requireNonNull(event, "event must not be null");
        Objects.requireNonNull(message, "message must not be null");
        event.reply(message).setEphemeral(true).queue();
    }

    /**
     * Sends an ephemeral follow-up message via the interaction's webhook hook, for use after
     * the interaction has already been acknowledged with an initial reply.
     *
     * @param event   the interaction whose hook should be used, must not be {@code null}
     * @param message the message data to send, must not be {@code null}
     */
    public static void sendEphemeralFollowUp(@NotNull IReplyCallback event, @NotNull MessageCreateData message) {
        Objects.requireNonNull(event, "event must not be null");
        Objects.requireNonNull(message, "message must not be null");
        event.getHook().sendMessage(message).setEphemeral(true).queue();
    }

    /**
     * Validates that a slash command was invoked from within a guild, replying with an
     * ephemeral error message if not.
     *
     * @param event             the slash command interaction event, must not be {@code null}
     * @param guildOnlyMessage  the ephemeral error message to send if there is no guild context,
     *                          must not be {@code null}
     * @return the guild the command was invoked in, or {@code null} if this command was not
     *         invoked from a guild (in which case an error reply has already been sent)
     */
    @Nullable
    public static Guild validateGuildContext(@NotNull SlashCommandInteractionEvent event, @NotNull String guildOnlyMessage) {
        Objects.requireNonNull(event, "event must not be null");
        Objects.requireNonNull(guildOnlyMessage, "guildOnlyMessage must not be null");
        Guild guild = event.getGuild();
        if (guild == null) {
            replyEphemeral(event, guildOnlyMessage);
        }
        return guild;
    }

    /**
     * Parses a UUID slash-command option, replying with an ephemeral error message if the value
     * is missing/blank or is not a valid UUID.
     *
     * @param event                the slash command interaction event, must not be {@code null}
     * @param rawValue              the raw option value to parse, may be {@code null} or blank
     * @param missingMessage        the ephemeral error message to send if {@code rawValue} is
     *                               missing or blank, must not be {@code null}
     * @param invalidFormatMessage  the ephemeral error message to send if {@code rawValue} is not
     *                               a valid UUID, must not be {@code null}
     * @return the parsed UUID, or {@link Optional#empty()} if parsing failed (in which case an
     *         error reply has already been sent)
     */
    @NotNull
    public static Optional<UUID> parseUuidOrReplyError(
            @NotNull SlashCommandInteractionEvent event,
            @Nullable String rawValue,
            @NotNull String missingMessage,
            @NotNull String invalidFormatMessage
    ) {
        Objects.requireNonNull(event, "event must not be null");
        Objects.requireNonNull(missingMessage, "missingMessage must not be null");
        Objects.requireNonNull(invalidFormatMessage, "invalidFormatMessage must not be null");

        if (rawValue == null || rawValue.isBlank()) {
            replyEphemeral(event, missingMessage);
            return Optional.empty();
        }

        try {
            return Optional.of(UUID.fromString(rawValue.strip()));
        } catch (IllegalArgumentException e) {
            replyEphemeral(event, invalidFormatMessage);
            return Optional.empty();
        }
    }

    /**
     * Sends an ephemeral header reply followed by one ephemeral follow-up embed per entry in
     * {@code embeds}, in order.
     *
     * @param event  the slash command interaction event, must not be {@code null}
     * @param header the initial ephemeral reply text, must not be {@code null}
     * @param embeds the embeds to send as follow-ups, in order, must not be {@code null}
     */
    public static void sendEphemeralEmbeds(
            @NotNull SlashCommandInteractionEvent event,
            @NotNull String header,
            @NotNull List<MessageCreateData> embeds
    ) {
        Objects.requireNonNull(event, "event must not be null");
        Objects.requireNonNull(header, "header must not be null");
        Objects.requireNonNull(embeds, "embeds must not be null");

        replyEphemeral(event, header);
        for (MessageCreateData embed : embeds) {
            sendEphemeralFollowUp(event, embed);
        }
    }

    /**
     * Sends an ephemeral header reply, acknowledging the interaction immediately, then maps each
     * item to a follow-up embed and sends it via the hook, skipping items that map to
     * {@code null}.
     *
     * <p>Prefer this overload over {@link #sendEphemeralEmbeds(SlashCommandInteractionEvent, String, List)}
     * when {@code embedMapper} performs blocking work (e.g. a synchronous Discord API lookup via
     * {@code .complete()}): acknowledging first ensures the reply is sent within Discord's 3-second
     * interaction window regardless of how long the mapping takes.
     *
     * @param event       the slash command interaction event, must not be {@code null}
     * @param header      the initial ephemeral reply text, must not be {@code null}
     * @param items       the items to map to embeds and send as follow-ups, in order, must not be {@code null}
     * @param embedMapper maps each item to a follow-up embed, or {@code null} to skip it, must not be {@code null}
     */
    public static <T> void sendEphemeralEmbeds(
            @NotNull SlashCommandInteractionEvent event,
            @NotNull String header,
            @NotNull List<T> items,
            @NotNull Function<T, MessageCreateData> embedMapper
    ) {
        Objects.requireNonNull(event, "event must not be null");
        Objects.requireNonNull(header, "header must not be null");
        Objects.requireNonNull(items, "items must not be null");
        Objects.requireNonNull(embedMapper, "embedMapper must not be null");

        replyEphemeral(event, header);
        for (T item : items) {
            MessageCreateData embed = embedMapper.apply(item);
            if (embed != null) {
                sendEphemeralFollowUp(event, embed);
            }
        }
    }
}
