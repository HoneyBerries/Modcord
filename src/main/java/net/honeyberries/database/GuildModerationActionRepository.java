package net.honeyberries.database;

import net.honeyberries.datatypes.action.ActionData;
import net.honeyberries.datatypes.action.ActionDataBuilder;
import net.honeyberries.datatypes.action.ActionType;
import net.honeyberries.datatypes.action.MessageDeletion;
import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.discord.MessageID;
import net.honeyberries.datatypes.discord.UserID;
import org.jetbrains.annotations.Nullable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

public class GuildModerationActionRepository {

    Logger logger = LoggerFactory.getLogger(GuildModerationActionRepository.class);
    private final Database database;

    public GuildModerationActionRepository() {
        this.database = Database.getInstance();
    }


    /**
     * Adds an action to the database.
     * @param actionData The action data to add
     * @return true if the action was added successfully, false otherwise
     */
    public boolean addActionToDatabase(ActionData actionData) {
        try {
            database.transaction(conn -> {
                // 1️⃣ Insert into guild_moderation_actions
                String insertActionSql = """
                    INSERT INTO guild_moderation_actions (
                        id, guild_id, user_id, action, reason,
                        timeout_duration, ban_duration
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """;

                try (PreparedStatement ps = conn.prepareStatement(insertActionSql)) {
                    ps.setObject(1, actionData.id());
                    ps.setLong(2, actionData.guildId().value());
                    ps.setLong(3, actionData.userId().value());
                    ps.setString(4, actionData.action().name());
                    ps.setString(5, actionData.reason());
                    ps.setLong(6, actionData.timeoutDuration());
                    ps.setLong(7, actionData.banDuration());
                    ps.executeUpdate();
                }

                // 2️⃣ Insert deletions into guild_moderation_action_deletions
                String insertDeletionSql = """
                    INSERT INTO guild_moderation_action_deletions (
                        action_id, channel_id, message_id
                    ) VALUES (?, ?, ?)
                """;

                try (PreparedStatement ps = conn.prepareStatement(insertDeletionSql)) {
                    for (MessageDeletion deletion : actionData.deletions()) {
                        ps.setObject(1, actionData.id());
                        ps.setLong(2, deletion.channelId().value());
                        ps.setLong(3, deletion.messageId().value());
                        ps.addBatch();
                    }
                    ps.executeBatch();
                }
            });

            return true;
        } catch (Exception e) {
            logger.error("Failed to add action to database", e);
            return false;
        }
    }


    @Nullable
    public ActionData getActionById(UUID actionId) {
        String sql = """
            SELECT *
            FROM guild_moderation_actions
            WHERE id = ?
        """;

        try {
            return database.query(conn -> {
                try (PreparedStatement ps = conn.prepareStatement(sql)) {
                    ps.setObject(1, actionId);

                    try (ResultSet rs = ps.executeQuery()) {
                        if (rs.next()) {
                            return mapAction(rs);
                        }
                        return null;
                    }
                }
            });
        } catch (Exception e) {
            logger.error("Failed to fetch action by id", e);
            return null;
        }
    }

    public List<ActionData> getActionsByGuild(long guildId) {
        String sql = """
            SELECT *
            FROM guild_moderation_actions
            WHERE guild_id = ?
            ORDER BY id DESC
        """;

        try {
            return database.query(conn -> {
                List<ActionData> actions = new ArrayList<>();

                try (PreparedStatement ps = conn.prepareStatement(sql)) {
                    ps.setLong(1, guildId);

                    try (ResultSet rs = ps.executeQuery()) {
                        while (rs.next()) {
                            actions.add(mapAction(rs));
                        }
                    }
                }

                return actions;
            });
        } catch (Exception e) {
            logger.error("Failed to fetch actions by guild", e);
            return List.of();
        }
    }

    public List<ActionData> getActionsByUser(long guildId, long userId) {
        String sql = """
            SELECT *
            FROM guild_moderation_actions
            WHERE guild_id = ? AND user_id = ?
            ORDER BY id DESC
        """;

        try {
            return database.query(conn -> {
                List<ActionData> actions = new ArrayList<>();

                try (PreparedStatement ps = conn.prepareStatement(sql)) {
                    ps.setLong(1, guildId);
                    ps.setLong(2, userId);

                    try (ResultSet rs = ps.executeQuery()) {
                        while (rs.next()) {
                            actions.add(mapAction(rs));
                        }
                    }
                }

                return actions;
            });
        } catch (Exception e) {
            logger.error("Failed to fetch actions by user", e);
            return List.of();
        }
    }

    public List<ActionData> getRecentActions(long guildId, int limit) {
        String sql = """
            SELECT *
            FROM guild_moderation_actions
            WHERE guild_id = ?
            ORDER BY id DESC
            LIMIT ?
        """;

        try {
            return database.query(conn -> {
                List<ActionData> actions = new ArrayList<>();

                try (PreparedStatement ps = conn.prepareStatement(sql)) {
                    ps.setLong(1, guildId);
                    ps.setInt(2, limit);

                    try (ResultSet rs = ps.executeQuery()) {
                        while (rs.next()) {
                            actions.add(mapAction(rs));
                        }
                    }
                }

                return actions;
            });
        } catch (Exception e) {
            logger.error("Failed to fetch recent actions", e);
            return List.of();
        }
    }

    private ActionData mapAction(ResultSet rs) throws SQLException {
        UUID actionId = (UUID) rs.getObject("id");

        ActionDataBuilder builder = new ActionDataBuilder(
            actionId,
            new GuildID(rs.getLong("guild_id")),
            new UserID(rs.getLong("user_id")),
            ActionType.valueOf(rs.getString("action")),
            rs.getString("reason"),
            rs.getLong("timeout_duration"),
            rs.getLong("ban_duration")
        );

        getDeletionsByActionId(actionId).forEach(builder::addMessageDeletion);

        return builder.build();
    }


    private List<MessageDeletion> getDeletionsByActionId(UUID actionId) {
    String sql = """
        SELECT channel_id, message_id
        FROM guild_moderation_action_deletions
        WHERE action_id = ?
    """;

    try {
        return database.query(conn -> {
            List<MessageDeletion> deletions = new ArrayList<>();

            try (PreparedStatement ps = conn.prepareStatement(sql)) {
                ps.setObject(1, actionId);

                try (ResultSet rs = ps.executeQuery()) {
                    while (rs.next()) {
                        ChannelID channelId = new ChannelID(rs.getLong("channel_id"));
                        MessageID messageId = new MessageID(rs.getLong("message_id"));

                        deletions.add(new MessageDeletion(channelId, messageId));
                    }
                }
            }

            return deletions;
        });
        } catch (Exception e) {
            logger.error("Failed to fetch deletions", e);
            return List.of();
        }
    }


}
