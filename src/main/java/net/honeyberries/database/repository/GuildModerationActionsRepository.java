package net.honeyberries.database.repository;

import net.honeyberries.database.Database;
import net.honeyberries.datatypes.action.ActionData;
import net.honeyberries.datatypes.action.ActionDataBuilder;
import net.honeyberries.datatypes.action.ActionType;
import net.honeyberries.datatypes.action.MessageDeletion;
import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.discord.MessageID;
import net.honeyberries.datatypes.discord.UserID;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

/**
 * Persists moderation actions and associated message deletions to the database.
 * Manages the lifecycle of {@link ActionData} instances, enabling retrieval by action ID, guild, or user.
 * Also handles transactional updates to ensure action records and their deletion specs remain synchronized.
 */
public class GuildModerationActionsRepository {

    /** Logger for recording database operations. */
    private final Logger logger = LoggerFactory.getLogger(GuildModerationActionsRepository.class);
    /** Singleton instance. */
    private static final GuildModerationActionsRepository INSTANCE = new GuildModerationActionsRepository();
    /** Database connection pool. */
    private final Database database;

    /**
     * Constructs a new repository, retrieving the singleton database instance.
     */
    public GuildModerationActionsRepository() {
        this.database = Database.getInstance();
    }

    /**
     * Retrieves the singleton instance of this repository.
     *
     * @return the singleton {@code GuildModerationActionsRepository}
     */
    @NotNull
    public static GuildModerationActionsRepository getInstance() {
        return INSTANCE;
    }

    /**
     * Persists an action record and its associated message deletions in a single transaction.
     * Both the action and all deletion specs are inserted; if either fails, the transaction is rolled back.
     *
     * @param actionData the moderation action to persist
     * @return {@code true} if both the action and deletions were inserted successfully, {@code false} if a database error occurred
     * @throws NullPointerException if {@code actionData} is {@code null}
     */
    public boolean addActionToDatabase(@NotNull ActionData actionData) {
        Objects.requireNonNull(actionData, "actionData must not be null");
        try {
            database.transaction(conn -> {
                String insertActionSql = """
                    INSERT INTO guild_moderation_actions (
                        action_id, guild_id, user_id, moderator_id, action, reason,
                        timeout_duration, ban_duration
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """;

                try (PreparedStatement ps = conn.prepareStatement(insertActionSql)) {
                    ps.setObject(1, actionData.id());
                    ps.setLong(2, actionData.guildId().value());
                    ps.setLong(3, actionData.userId().value());
                    ps.setLong(4, actionData.moderatorId().value());
                    ps.setString(5, actionData.action().name());
                    ps.setString(6, actionData.reason());
                    ps.setLong(7, actionData.timeoutDuration());
                    ps.setLong(8, actionData.banDuration());
                    ps.executeUpdate();
                }

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

    /**
     * Retrieves a stored action by its unique identifier.
     *
     * @param actionId the action UUID to look up
     * @return the {@code ActionData} if found, or {@code null} if no matching action exists or a database error occurred
     * @throws NullPointerException if {@code actionId} is {@code null}
     */
    @Nullable
    public ActionData getActionById(@NotNull UUID actionId) {
        Objects.requireNonNull(actionId, "actionId must not be null");
        String sql = """
            SELECT *
            FROM guild_moderation_actions
            WHERE action_id = ?
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
            logger.error("Failed to fetch action by interactionID", e);
            return null;
        }
    }

    /**
     * Fetches all actions targeted at users in a specific guild, ordered newest first.
     * Returns an empty list if no actions are found or if a database error occurs.
     *
     * @param guildId the guild to search for actions
     * @return a list of {@code ActionData} in reverse chronological order, never {@code null}
     * @throws NullPointerException if {@code guildId} is {@code null}
     */
    @NotNull
    public List<ActionData> getActionsByGuild(@NotNull GuildID guildId) {
        Objects.requireNonNull(guildId, "guildId must not be null");
        String sql = """
            SELECT *
            FROM guild_moderation_actions
            WHERE guild_id = ?
            ORDER BY action_id DESC
        """;

        try {
            return database.query(conn -> {
                List<ActionData> actions = new ArrayList<>();

                try (PreparedStatement ps = conn.prepareStatement(sql)) {
                    ps.setLong(1, guildId.value());

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

    /**
     * Fetches all actions targeted at a specific user within a guild, ordered newest first.
     * Returns an empty list if no actions are found or if a database error occurs.
     *
     * @param guildId the guild ID to search in
     * @param userId the user ID to match
     * @return a list of {@code ActionData} in reverse chronological order, never {@code null}
     */
    @NotNull
    public List<ActionData> getActionsByUser(GuildID guildId, UserID userId) {
        String sql = """
            SELECT *
            FROM guild_moderation_actions
            WHERE guild_id = ? AND user_id = ?
            ORDER BY action_id DESC
        """;

        try {
            return database.query(conn -> {
                List<ActionData> actions = new ArrayList<>();

                try (PreparedStatement ps = conn.prepareStatement(sql)) {
                    ps.setLong(1, guildId.value());
                    ps.setLong(2, userId.value());

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

    /**
     * Fetches all actions targeted at a specific user across all guilds, ordered newest first.
     * Used by the appeal system in DMs where the user may be banned from some guilds.
     * Returns an empty list if no actions are found or if a database error occurs.
     *
     * @param userId the user ID to match
     * @return a list of {@code ActionData} in reverse chronological order, never {@code null}
     */
    @NotNull
    public List<ActionData> getAllActionsByUser(UserID userId) {
        String sql = """
            SELECT *
            FROM guild_moderation_actions
            WHERE user_id = ?
            ORDER BY action_id DESC
        """;

        try {
            return database.query(conn -> {
                List<ActionData> actions = new ArrayList<>();

                try (PreparedStatement ps = conn.prepareStatement(sql)) {
                    ps.setLong(1, userId.value());

                    try (ResultSet rs = ps.executeQuery()) {
                        while (rs.next()) {
                            actions.add(mapAction(rs));
                        }
                    }
                }

                return actions;
            });
        } catch (Exception e) {
            logger.error("Failed to fetch actions by user across all guilds", e);
            return List.of();
        }
    }

    /**
     * Fetches all actions in a guild that have not yet been reversed, ordered newest first.
     * Used by the rollback command to present candidates to moderators.
     *
     * @param guildId guild to fetch actions from, must not be {@code null}
     * @return list of active (non-reversed) actions, never {@code null}
     * @throws NullPointerException if {@code guildId} is {@code null}
     */
    @NotNull
    public List<ActionData> getActiveActions(@NotNull GuildID guildId) {
        Objects.requireNonNull(guildId, "guildId must not be null");
        String sql = """
            SELECT gma.*
            FROM guild_moderation_actions gma
            WHERE gma.guild_id = ?
              AND NOT EXISTS (
                    SELECT 1 FROM guild_moderation_action_reversals r
                    WHERE r.action_id = gma.action_id
                  )
            ORDER BY gma.action_id DESC
        """;

        try {
            return database.query(conn -> {
                List<ActionData> actions = new ArrayList<>();

                try (PreparedStatement ps = conn.prepareStatement(sql)) {
                    ps.setLong(1, guildId.value());

                    try (ResultSet rs = ps.executeQuery()) {
                        while (rs.next()) {
                            actions.add(mapAction(rs));
                        }
                    }
                }

                return actions;
            });
        } catch (Exception e) {
            logger.error("Failed to fetch active actions for guild {}", guildId, e);
            return List.of();
        }
    }

    /**
     * Retrieves the most recent active (non-reversed, non-NULL) moderation actions for a guild, up to the specified limit.
     * Excludes actions that have been reversed and NULL actions.
     * Returns an empty list if no actions are found or if a database error occurs.
     *
     * @param guildId the guild to fetch actions from
     * @param limit the maximum number of actions to return
     * @return a list of recent active {@code ActionData} up to {@code limit} in size, ordered newest first, never {@code null}
     */
    @NotNull
    public List<ActionData> getRecentActions(GuildID guildId, int limit) {
        String sql = """
            SELECT gma.*
            FROM guild_moderation_actions gma
            WHERE gma.guild_id = ?
              AND gma.action != 'NULL'
              AND NOT EXISTS (
                    SELECT 1 FROM guild_moderation_action_reversals r
                    WHERE r.action_id = gma.action_id
                  )
            ORDER BY gma.action_id DESC
            LIMIT ?
        """;

        try {
            return database.query(conn -> {
                List<ActionData> actions = new ArrayList<>();

                try (PreparedStatement ps = conn.prepareStatement(sql)) {
                    ps.setLong(1, guildId.value());
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

    /**
     * Reconstructs an {@code ActionData} instance from a database result row.
     * Fetches associated message deletions and populates them into the action builder.
     *
     * @param rs the result set positioned at a row from guild_moderation_actions
     * @return the reconstructed {@code ActionData}
     * @throws SQLException if a column cannot be accessed
     */
    @NotNull
    private ActionData mapAction(@NotNull ResultSet rs) throws SQLException {
        Objects.requireNonNull(rs, "rs must not be null");
        UUID actionId = (UUID) rs.getObject("action_id");

        ActionDataBuilder builder = new ActionDataBuilder(
            actionId,
            new GuildID(rs.getLong("guild_id")),
            new UserID(rs.getLong("user_id")),
            new UserID(rs.getLong("moderator_id")),
            ActionType.valueOf(rs.getString("action")),
            rs.getString("reason"),
            rs.getLong("timeout_duration"),
            rs.getLong("ban_duration")
        );

        getDeletionsByActionId(actionId).forEach(builder::addMessageDeletion);

        return builder.build();
    }

    /**
     * Retrieves all message deletion specs associated with a moderation action.
     * Returns an empty list if no deletions are found or if a database error occurs.
     *
     * @param actionId the action ID to fetch deletions for
     * @return a list of {@code MessageDeletion} instances, never {@code null}
     * @throws NullPointerException if {@code actionId} is {@code null}
     */
    @NotNull
    private List<MessageDeletion> getDeletionsByActionId(@NotNull UUID actionId) {
        Objects.requireNonNull(actionId, "actionId must not be null");
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

    /**
     * Persists a reversal record so the unban watcher and future queries know the action was undone.
     *
     * @param actionId the UUID of the action that was reversed, must not be {@code null}
     * @param reason   human-readable reversal note, must not be {@code null}
     * @throws NullPointerException if {@code actionId} or {@code reason} is {@code null}
     */
    public void recordReversal(@NotNull UUID actionId, @NotNull String reason) {
        Objects.requireNonNull(actionId, "actionId must not be null");
        Objects.requireNonNull(reason, "reason must not be null");
        String sql = """
            INSERT INTO guild_moderation_action_reversals (action_id, reason, reversed_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT (action_id) DO UPDATE SET
                reason      = EXCLUDED.reason,
                reversed_at = EXCLUDED.reversed_at
        """;
        try {
            database.transaction(conn -> {
                try (PreparedStatement ps = conn.prepareStatement(sql)) {
                    ps.setObject(1, actionId);
                    ps.setString(2, reason);
                    ps.executeUpdate();
                }
            });
        } catch (Exception e) {
            logger.warn("Failed to record reversal for action {}", actionId, e);
        }
    }

}
