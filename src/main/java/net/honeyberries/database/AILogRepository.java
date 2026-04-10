package net.honeyberries.database;

import com.openai.models.chat.completions.ChatCompletionMessageParam;
import net.honeyberries.datatypes.discord.GuildID;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ArrayNode;

import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

/**
 * Repository for AI moderation logs stored in the database.
 * Tracks AI detection events, inference results, and moderation decisions for audit and analysis purposes.
 * Provides methods to persist, retrieve, and query AI activity logs scoped by guild and user.
 */
public class AILogRepository {

	/** Jackson object mapper for serialization. */
	private static final ObjectMapper objectMapper = new ObjectMapper();

	/** Immutable representation of one AI log row. */
	public record AILogEntry(
			@NotNull UUID interactionId,
			@NotNull GuildID guildId,
			@NotNull ArrayNode conversation,
			@NotNull OffsetDateTime timestamp
	) {}

	/** Logger for recording database operations. */
	private final Logger logger = LoggerFactory.getLogger(AILogRepository.class);
	/** Database connection pool. */
	private final Database database;
	/** Singleton instance. */
	private static final AILogRepository INSTANCE = new AILogRepository();

	/**
	 * Retrieves the singleton instance of this repository.
	 *
	 * @return the singleton {@code AILogRepository}
	 */
	@NotNull
	public static AILogRepository getInstance() {
		return INSTANCE;
	}

	/**
	 * Constructs a new repository, retrieving the singleton database instance.
	 */
	public AILogRepository() {
		this.database = Database.getInstance();
	}

	/**
	 * Persists one AI moderation log row for a guild.
	 *
	 * @param guildId the guild scope for this inference log
	 * @param conversation list of ChatCompletionMessageParams representing the full conversation
	 * @return {@code true} if the row was inserted, {@code false} if a database error occurred
	 * @throws NullPointerException if any parameter is {@code null}
	 */
	public boolean addLogEntry(@NotNull GuildID guildId, @NotNull List<ChatCompletionMessageParam> conversation) {
		Objects.requireNonNull(guildId, "guildId must not be null");
		Objects.requireNonNull(conversation, "conversation must not be null");

		String sql = """
			INSERT INTO ai_log (guild_id, interaction)
			VALUES (?, CAST(? AS JSONB))
		""";

		try {
			// Serialize the conversation list into a JSON array
			ArrayNode conversationArray = objectMapper.createArrayNode();
			for (ChatCompletionMessageParam message : conversation) {
				conversationArray.add(objectMapper.valueToTree(message));
			}
			String jsonString = objectMapper.writeValueAsString(conversationArray);

			database.transaction(conn -> {
				try (PreparedStatement ps = conn.prepareStatement(sql)) {
					ps.setLong(1, guildId.value());
					ps.setString(2, jsonString);
					ps.executeUpdate();
				}
			});
			return true;
		} catch (Exception e) {
			logger.error("Failed to insert AI log entry", e);
			return false;
		}
	}

	/**
	 * Retrieves one AI log entry by its primary key.
	 *
	 * @param interactionId the log entry interaction UUID
	 * @return the matching {@code AILogEntry}, or {@code null} if missing or on database error
	 * @throws NullPointerException if {@code interactionId} is {@code null}
	 */
	@Nullable
	public AILogEntry getLogEntryById(@NotNull UUID interactionId) {
		Objects.requireNonNull(interactionId, "interactionId must not be null");
		String sql = """
			SELECT interaction_id, guild_id, interaction, timestamp
			FROM ai_log
			WHERE interaction_id = ?
		""";

		try {
			return database.query(conn -> {
				try (PreparedStatement ps = conn.prepareStatement(sql)) {
					ps.setObject(1, interactionId);
					try (ResultSet rs = ps.executeQuery()) {
						if (rs.next()) {
							return mapEntry(rs);
						}
						return null;
					}
				}
			});
		} catch (Exception e) {
			logger.error("Failed to fetch AI log entry by interactionId", e);
			return null;
		}
	}

	/**
	 * Retrieves the most recent AI log rows for a guild.
	 *
	 * @param guildId the guild scope
	 * @param limit the maximum number of rows to return; values less than 1 return an empty list
	 * @return recent log rows ordered newest-first, or an empty list if none found or on database error
	 * @throws NullPointerException if {@code guildId} is {@code null}
	 */
	@NotNull
	public List<AILogEntry> getRecentLogEntriesByGuild(@NotNull GuildID guildId, int limit) {
		Objects.requireNonNull(guildId, "guildId must not be null");
		if (limit < 1) {
			return List.of();
		}

		String sql = """
			SELECT interaction_id, guild_id, interaction, timestamp
			FROM ai_log
			WHERE guild_id = ?
			ORDER BY timestamp DESC
			LIMIT ?
		""";

		try {
			return database.query(conn -> {
				List<AILogEntry> entries = new ArrayList<>();

				try (PreparedStatement ps = conn.prepareStatement(sql)) {
					ps.setLong(1, guildId.value());
					ps.setInt(2, limit);

					try (ResultSet rs = ps.executeQuery()) {
						while (rs.next()) {
							entries.add(mapEntry(rs));
						}
					}
				}

				return entries;
			});
		} catch (Exception e) {
			logger.error("Failed to fetch recent AI log entries by guild", e);
			return List.of();
		}
	}

	/**
	 * Reconstructs an {@code AILogEntry} from a database row.
	 *
	 * @param rs result set positioned on an {@code ai_log} row
	 * @return reconstructed entry
	 * @throws SQLException if a column cannot be accessed
	 */
	@NotNull
	private AILogEntry mapEntry(@NotNull ResultSet rs) throws SQLException {
		Objects.requireNonNull(rs, "rs must not be null");
		return new AILogEntry(
				(UUID) rs.getObject("interaction_id"),
				new GuildID(rs.getLong("guild_id")),
				(ArrayNode) objectMapper.readTree(rs.getString("interaction")),
				rs.getObject("timestamp", OffsetDateTime.class)
		);
	}
}
