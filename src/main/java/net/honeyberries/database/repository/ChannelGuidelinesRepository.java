package net.honeyberries.database.repository;

import net.honeyberries.database.Database;
import net.honeyberries.datatypes.content.ChannelGuidelines;
import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.Types;
import java.util.Objects;

/**
 * Persists and retrieves channel-specific moderation guidelines from the database.
 * Supports upsert operations to synchronize guidelines with Discord channel metadata.
 * Uses a composite key of guild ID and channel ID to uniquely identify guideline entries.
 */
public class ChannelGuidelinesRepository {

    /** Logger for recording database operations. */
    private final Logger logger = LoggerFactory.getLogger(ChannelGuidelinesRepository.class);
    /** Database connection pool. */
    private final Database database = Database.getInstance();
    /** Singleton instance. */
    private static final ChannelGuidelinesRepository INSTANCE = new ChannelGuidelinesRepository();

    /**
     * Retrieves the singleton instance of this repository.
     *
     * @return the singleton {@code ChannelGuidelinesRepository}
     */
    @NotNull
    public static ChannelGuidelinesRepository getInstance() {
        return INSTANCE;
    }

    /**
     * Persists or updates channel guidelines for a specific guild and channel.
     * If guidelines for that guild/channel pair already exist, they are replaced; otherwise, new guidelines are inserted.
     *
     * @param channelGuidelines the guidelines to persist or update
     * @return {@code true} if the operation succeeded, {@code false} if a database error occurred
     * @throws NullPointerException if {@code channelGuidelines} is {@code null}
     */
    public boolean addOrReplaceChannelGuidelinesToDatabase(@NotNull ChannelGuidelines channelGuidelines) {
        Objects.requireNonNull(channelGuidelines, "channelGuidelines must not be null");
        try {
            database.transaction(conn -> {
                String sql = """
                    INSERT INTO guild_channel_guidelines (guild_id, channel_id, guidelines)
                    VALUES (?, ?, ?)
                    ON CONFLICT (guild_id, channel_id) DO UPDATE SET
                        guidelines = EXCLUDED.guidelines
                """;

                try (PreparedStatement ps = conn.prepareStatement(sql)) {
                    ps.setLong(1, channelGuidelines.guildId().value());
                    ps.setLong(2, channelGuidelines.channelId().value());
                    if (channelGuidelines.guidelinesText() != null) {
                        ps.setString(3, channelGuidelines.guidelinesText());
                    } else {
                        ps.setNull(3, Types.VARCHAR);
                    }
                    ps.executeUpdate();
                }
            });
            return true;
        } catch (Exception e) {
            logger.error("Failed to add/update channel guidelines in database", e);
            return false;
        }
    }

    /**
     * Retrieves channel guidelines for a specific guild and channel.
     *
     * @param guildId the guild ID to search in
     * @param channelId the channel ID to look up
     * @return the {@code ChannelGuidelines} if found, or {@code null} if no matching entry exists or a database error occurred
     * @throws NullPointerException if {@code guildId} or {@code channelId} is {@code null}
     */
    @Nullable
    public ChannelGuidelines getChannelGuidelines(@NotNull GuildID guildId, @NotNull ChannelID channelId) {
        Objects.requireNonNull(guildId, "guildId must not be null");
        Objects.requireNonNull(channelId, "channelId must not be null");
        String sql = """
            SELECT guild_id, channel_id, guidelines
            FROM guild_channel_guidelines
            WHERE guild_id = ? AND channel_id = ?
        """;

        try {
            return database.query(conn -> {
                try (PreparedStatement ps = conn.prepareStatement(sql)) {
                    ps.setLong(1, guildId.value());
                    ps.setLong(2, channelId.value());
                    try (ResultSet rs = ps.executeQuery()) {
                        if (rs.next()) {
                            return new ChannelGuidelines(
                                    new GuildID(rs.getLong("guild_id")),
                                    new ChannelID(rs.getLong("channel_id")),
                                    rs.getString("guidelines")
                            );
                        } else {
                            return null;
                        }
                    }
                }
            });
        } catch (Exception e) {
            logger.error("Failed to retrieve channel guidelines from database", e);
            return null;
        }
    }

}
