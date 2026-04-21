package net.honeyberries.database.repository;

import net.honeyberries.database.Database;
import net.honeyberries.datatypes.content.ModerationMessage;
import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.discord.MessageID;
import net.honeyberries.datatypes.discord.UserID;
import org.jetbrains.annotations.NotNull;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

/**
 * Persists and restores the in-memory moderation message queue across bot restarts.
 * <p>
 * When the bot shuts down, {@link #saveMessages} writes all pending (un-processed) messages
 * to the {@code pending_moderation_messages} table. On the next startup the queue is read
 * back via {@link #loadMessages} so no messages that arrived before the restart are silently lost.
 * Once messages are re-loaded they are deleted from the table ({@link #clearMessages}) so they
 * are not replayed again.
 */
public class PendingMessageRepository {

    private static final Logger logger = LoggerFactory.getLogger(PendingMessageRepository.class);
    private static final PendingMessageRepository INSTANCE = new PendingMessageRepository();
    private final Database database = Database.getInstance();

    private PendingMessageRepository() {}

    /**
     * Returns the singleton instance.
     *
     * @return the singleton {@code PendingMessageRepository}
     */
    @NotNull
    public static PendingMessageRepository getInstance() {
        return INSTANCE;
    }

    /**
     * Persists a collection of pending messages for the given guild.
     * Existing rows for the guild are replaced; this is a full snapshot, not an append.
     *
     * @param guildId  the guild whose queue is being saved, must not be {@code null}
     * @param messages the messages to persist, must not be {@code null}
     * @throws NullPointerException if {@code guildId} or {@code messages} is {@code null}
     */
    public void saveMessages(@NotNull GuildID guildId, @NotNull List<ModerationMessage> messages) {
        Objects.requireNonNull(guildId, "guildId must not be null");
        Objects.requireNonNull(messages, "messages must not be null");
        if (messages.isEmpty()) return;

        String deleteSql = "DELETE FROM pending_moderation_messages WHERE guild_id = ?";
        String insertSql = """
            INSERT INTO pending_moderation_messages
                (guild_id, message_id, user_id, channel_id, content, message_timestamp, is_history)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (guild_id, message_id) DO NOTHING
        """;

        try {
            database.transaction(conn -> {
                try (PreparedStatement del = conn.prepareStatement(deleteSql)) {
                    del.setLong(1, guildId.value());
                    del.executeUpdate();
                }
                try (PreparedStatement ins = conn.prepareStatement(insertSql)) {
                    for (ModerationMessage msg : messages) {
                        ins.setLong(1, guildId.value());
                        ins.setLong(2, msg.messageId().value());
                        ins.setLong(3, msg.userId().value());
                        ins.setLong(4, msg.channelId().value());
                        ins.setString(5, msg.content());
                        ins.setTimestamp(6, Timestamp.valueOf(msg.timestamp()));
                        ins.setBoolean(7, msg.isHistoryContextWindow());
                        ins.addBatch();
                    }
                    ins.executeBatch();
                }
            });
            logger.info("Saved {} pending messages for guild {}", messages.size(), guildId);
        } catch (Exception e) {
            logger.error("Failed to save pending messages for guild {}", guildId, e);
        }
    }


    /**
     * Loads all persisted pending messages for a guild.
     * Call {@link #clearMessages(GuildID)} after re-queuing the returned messages so they are
     * not replayed on subsequent restarts.
     *
     * @param guildId the guild to load messages for, must not be {@code null}
     * @return list of {@link ModerationMessage} records, never {@code null}
     * @throws NullPointerException if {@code guildId} is {@code null}
     */
    @NotNull
    public List<ModerationMessage> loadMessages(@NotNull GuildID guildId) {
        Objects.requireNonNull(guildId, "guildId must not be null");
        String sql = """
            SELECT message_id, user_id, channel_id, content, message_timestamp, is_history
            FROM pending_moderation_messages
            WHERE guild_id = ?
            ORDER BY message_timestamp
        """;

        try {
            return database.query(conn -> {
                List<ModerationMessage> results = new ArrayList<>();
                try (PreparedStatement ps = conn.prepareStatement(sql)) {
                    ps.setLong(1, guildId.value());
                    try (ResultSet rs = ps.executeQuery()) {
                        while (rs.next()) {
                            LocalDateTime ts = rs.getTimestamp("message_timestamp").toLocalDateTime();
                            results.add(new ModerationMessage(
                                    new MessageID(rs.getLong("message_id")),
                                    new UserID(rs.getLong("user_id")),
                                    rs.getString("content"),
                                    ts,
                                    guildId,
                                    new ChannelID(rs.getLong("channel_id")),
                                    List.of(),
                                    rs.getBoolean("is_history")
                            ));
                        }
                    }
                }
                return results;
            });
        } catch (Exception e) {
            logger.error("Failed to load pending messages for guild {}", guildId, e);
            return List.of();
        }
    }


    /**
     * Deletes all persisted pending messages for a guild.
     * Call this after successfully re-queuing the messages returned by {@link #loadMessages}.
     *
     * @param guildId the guild to clear, must not be {@code null}
     * @throws NullPointerException if {@code guildId} is {@code null}
     */
    public void clearMessages(@NotNull GuildID guildId) {
        Objects.requireNonNull(guildId, "guildId must not be null");
        String sql = "DELETE FROM pending_moderation_messages WHERE guild_id = ?";
        try {
            database.transaction(conn -> {
                try (PreparedStatement ps = conn.prepareStatement(sql)) {
                    ps.setLong(1, guildId.value());
                    ps.executeUpdate();
                }
            });
        } catch (Exception e) {
            logger.error("Failed to clear pending messages for guild {}", guildId, e);
        }
    }
}
