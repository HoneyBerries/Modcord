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

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;

/**
 * Persists moderation actions and associated message deletions to the database.
 * Manages the lifecycle of {@link ActionData} instances, enabling retrieval by action ID, guild, or user.
 * Also handles transactional updates to ensure action records and their deletion specs remain synchronized.
 */
public class GuildModerationActionsRepository extends RepositoryBase {

    /**
     * Singleton instance.
     */
    private static final GuildModerationActionsRepository INSTANCE = new GuildModerationActionsRepository();

    /**
     * Constructs a new repository, retrieving the singleton database instance.
     */
    public GuildModerationActionsRepository() {
        super();
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

        return safeTransaction(conn -> {
            String insertActionSql = """
                        INSERT INTO guild_moderation_actions (
                            action_id, guild_id, user_id, moderator_id, action, reason,
                            timeout_duration, ban_duration, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                ps.setTimestamp(9, Timestamp.from(actionData.timestamp()));
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
        }, "Failed to add action to database");
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

        List<ActionData> results = queryActionsWithDeletions(sql, ps -> ps.setObject(1, actionId),
                "Failed to fetch action by interactionID", actionId);
        return results.isEmpty() ? null : results.get(0);
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
                    ORDER BY created_at DESC
                """;

        return queryActionsWithDeletions(sql, ps -> ps.setLong(1, guildId.value()),
                "Failed to fetch actions by guild", guildId);
    }

    /**
     * Fetches all actions targeted at a specific user within a guild, ordered newest first.
     * Returns an empty list if no actions are found or if a database error occurs.
     *
     * @param guildId the guild ID to search in
     * @param userId  the user ID to match
     * @return a list of {@code ActionData} in reverse chronological order, never {@code null}
     */
    @NotNull
    public List<ActionData> getActionsByUser(GuildID guildId, UserID userId) {
        String sql = """
                    SELECT *
                    FROM guild_moderation_actions
                    WHERE guild_id = ? AND user_id = ?
                    ORDER BY created_at DESC
                """;

        return queryActionsWithDeletions(sql, ps -> {
            ps.setLong(1, guildId.value());
            ps.setLong(2, userId.value());
        }, "Failed to fetch actions by user", guildId, userId);
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
                    ORDER BY created_at DESC
                """;

        return queryActionsWithDeletions(sql, ps -> ps.setLong(1, userId.value()),
                "Failed to fetch actions by user across all guilds", userId);
    }


    /**
     * Retrieves the most recent active (non-reversed, non-NULL) moderation actions for a guild, up to the specified limit.
     * Excludes actions that have been reversed and NULL actions.
     * Returns an empty list if no actions are found or if a database error occurs.
     *
     * @param guildId the guild to fetch actions from
     * @param limit   the maximum number of actions to return
     * @return a list of recent active {@code ActionData} up to {@code limit} in size, ordered newest first, never {@code null}
     */
    @NotNull
    public List<ActionData> getRecentActiveActions(GuildID guildId, int limit) {
        String sql = """
                    SELECT gma.*
                    FROM guild_moderation_actions gma
                    WHERE gma.guild_id = ?
                      AND gma.action != 'NULL'
                      AND NOT EXISTS (
                            SELECT 1 FROM guild_moderation_action_reversals r
                            WHERE r.action_id = gma.action_id
                          )
                    ORDER BY gma.created_at DESC
                    LIMIT ?
                """;

        return queryActionsWithDeletions(sql, ps -> {
            ps.setLong(1, guildId.value());
            ps.setInt(2, limit);
        }, "Failed to fetch recent actions", guildId, limit);
    }

    /**
     * Runs a {@code guild_moderation_actions} query and attaches each row's message deletions,
     * fetching all deletions for the result set in a single batched follow-up query instead of one
     * query per action (avoids an N+1 query pattern for list-returning lookups).
     *
     * @param sql          the {@code guild_moderation_actions} SELECT to run
     * @param binder       binds the SQL's placeholders
     * @param errorMessage SLF4J-style error message logged on failure
     * @param errorArgs    values substituted into {@code errorMessage}
     * @return matching actions with deletions populated, in result-set order, never {@code null}
     */
    @NotNull
    private List<ActionData> queryActionsWithDeletions(
            @NotNull String sql,
            Database.StatementBinder binder,
            @NotNull String errorMessage,
            Object... errorArgs
    ) {
        return safeQueryForList(conn -> {
            List<ActionRow> rows = fetchList(conn, sql, binder, this::mapActionRow);
            return attachDeletionsAndBuild(conn, rows);
        }, errorMessage, errorArgs);
    }

    /**
     * A partially built action (row data mapped, deletions not yet attached) paired with the action ID
     * used to look up its deletions. {@link ActionDataBuilder} does not expose an id getter, so the id
     * extracted while mapping the row is carried alongside it.
     */
    private record ActionRow(@NotNull UUID id, @NotNull ActionDataBuilder builder) {}

    /**
     * Maps one {@code guild_moderation_actions} row into an {@link ActionRow}, without deletions.
     *
     * @param rs the result set positioned at a row from guild_moderation_actions
     * @return the row's id and a builder populated with its core fields
     * @throws SQLException if a column cannot be accessed
     */
    @NotNull
    private ActionRow mapActionRow(@NotNull ResultSet rs) throws SQLException {
        Objects.requireNonNull(rs, "rs must not be null");
        UUID actionId = (UUID) rs.getObject("action_id");

        ActionDataBuilder builder = new ActionDataBuilder(
                actionId,
                rs.getTimestamp("created_at").toInstant(),
                new GuildID(rs.getLong("guild_id")),
                new UserID(rs.getLong("user_id")),
                new UserID(rs.getLong("moderator_id")),
                ActionType.valueOf(rs.getString("action")),
                rs.getString("reason"),
                rs.getLong("timeout_duration"),
                rs.getLong("ban_duration")
        );

        return new ActionRow(actionId, builder);
    }

    /**
     * Batch-fetches message deletions for every action in {@code rows} in a single query (instead of
     * one query per action) and attaches each action's deletions to its builder before building the
     * final {@link ActionData} list.
     *
     * @param conn the connection to run the batched deletions query on
     * @param rows the mapped rows (without deletions) to complete, in the order they should be returned
     * @return completed actions, in the same order as {@code rows}
     * @throws SQLException if the deletions query fails
     */
    @NotNull
    private List<ActionData> attachDeletionsAndBuild(@NotNull Connection conn, @NotNull List<ActionRow> rows) throws SQLException {
        if (rows.isEmpty()) {
            return List.of();
        }

        UUID[] actionIds = rows.stream().map(ActionRow::id).toArray(UUID[]::new);
        Map<UUID, List<MessageDeletion>> deletionsByAction = new HashMap<>();

        String sql = """
                    SELECT action_id, channel_id, message_id
                    FROM guild_moderation_action_deletions
                    WHERE action_id = ANY(?)
                """;

        try (PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setArray(1, conn.createArrayOf("uuid", actionIds));

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    UUID actionId = (UUID) rs.getObject("action_id");
                    ChannelID channelId = new ChannelID(rs.getLong("channel_id"));
                    MessageID messageId = new MessageID(rs.getLong("message_id"));
                    deletionsByAction
                            .computeIfAbsent(actionId, k -> new ArrayList<>())
                            .add(new MessageDeletion(channelId, messageId));
                }
            }
        }

        List<ActionData> actions = new ArrayList<>(rows.size());
        for (ActionRow row : rows) {
            for (MessageDeletion deletion : deletionsByAction.getOrDefault(row.id(), List.of())) {
                row.builder().addMessageDeletion(deletion);
            }
            actions.add(row.builder().build());
        }
        return actions;
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

        safeTransaction(conn -> {
            try (PreparedStatement ps = conn.prepareStatement(sql)) {
                ps.setObject(1, actionId);
                ps.setString(2, reason);
                ps.executeUpdate();
            }
        }, "Failed to record reversal for action {}", actionId);
    }

}
