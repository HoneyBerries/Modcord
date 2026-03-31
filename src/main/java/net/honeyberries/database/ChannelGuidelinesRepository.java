package net.honeyberries.database;

import net.honeyberries.datatypes.content.ChannelGuidelines;
import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import org.jetbrains.annotations.Nullable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.sql.PreparedStatement;
import java.sql.ResultSet;

public class ChannelGuidelinesRepository {

    private final Logger logger = LoggerFactory.getLogger(ChannelGuidelinesRepository.class);
    private final Database database = Database.getInstance();

    private static final ChannelGuidelinesRepository INSTANCE = new ChannelGuidelinesRepository();

    public static ChannelGuidelinesRepository getInstance() {
        return INSTANCE;
    }


    public boolean addOrReplaceChannelGuidelinesToDatabase(ChannelGuidelines channelGuidelines) {
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
                        ps.setNull(3, java.sql.Types.VARCHAR);
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

    @Nullable
    public ChannelGuidelines getChannelGuidelines(GuildID guildId, ChannelID channelId) {
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
