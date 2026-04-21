package net.honeyberries.database.repository;

import net.dv8tion.jda.api.entities.User;
import net.honeyberries.database.Database;
import net.honeyberries.datatypes.discord.DiscordUser;
import net.honeyberries.datatypes.discord.UserID;
import org.jetbrains.annotations.NotNull;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.util.Objects;

/**
 * Repository for the global special-user backdoor stored in {@code special_users}.
 *
 * <p>This table is intentionally not guild-scoped. It is used for trusted operators,
 * troubleshooting access, and other controlled support workflows where the bot should
 * treat a Discord account as specially recognized regardless of server membership.
 * The repository keeps the stored username in sync with the user's snowflake.
 */
public class SpecialUsersRepository {

	/** Logger for recording database operations. */
	private final Logger logger = LoggerFactory.getLogger(SpecialUsersRepository.class);
	/** Database connection pool. */
	private final Database database;
	/** Singleton instance. */
	private static final SpecialUsersRepository INSTANCE = new SpecialUsersRepository();

	/**
	 * Retrieves the singleton instance of this repository.
	 *
	 * @return the singleton {@code SpecialUsersRepository}
	 */
	@NotNull
	public static SpecialUsersRepository getInstance() {
		return INSTANCE;
	}

	/**
	 * Constructs a new repository backed by the shared {@link Database} singleton.
	 */
	public SpecialUsersRepository() {
		this.database = Database.getInstance();
	}

	/**
	 * Checks whether the provided user is present in the special-user backdoor table.
	 *
	 * @param userID the user to check, must not be {@code null}
	 * @return {@code true} if the user exists in {@code special_users}, {@code false} otherwise or if a database error occurs
	 * @throws NullPointerException if {@code userID} is {@code null}
	 */
	public boolean isSpecialUser(@NotNull UserID userID) {
		Objects.requireNonNull(userID, "userID must not be null");
		String sql = """
			SELECT 1
			FROM special_users
			WHERE user_id = ?
			LIMIT 1
		""";

		try {
			return database.query(conn -> {
				try (PreparedStatement ps = conn.prepareStatement(sql)) {
					ps.setLong(1, userID.value());

					try (ResultSet rs = ps.executeQuery()) {
						return rs.next();
					}
				}
			});
		} catch (Exception e) {
			logger.error("Failed to check special user", e);
			return false;
		}
	}


	public boolean isSpecialUser(@NotNull User user) {
		Objects.requireNonNull(user, "user must not be null");
		return isSpecialUser(UserID.fromUser(user));
	}

	/**
	 * Inserts or refreshes a special-user record.
	 *
	 * <p>The operation is idempotent; existing rows are updated with the latest username.
	 *
	 * @param discordUser the user identifier and username to store, must not be {@code null}
	 * @return {@code true} if the operation succeeds, {@code false} if a database error occurs
	 * @throws NullPointerException if {@code discordUser} is {@code null}
	 */
	public boolean addOrUpdateSpecialUser(@NotNull DiscordUser discordUser) {
		Objects.requireNonNull(discordUser, "discordUser must not be null");
		String sql = """
			INSERT INTO special_users (user_id, username)
			VALUES (?, ?)
			ON CONFLICT (user_id) DO UPDATE SET
				username = EXCLUDED.username
		""";

		try {
			database.transaction(conn -> {
				try (PreparedStatement ps = conn.prepareStatement(sql)) {
					ps.setLong(1, discordUser.userId().value());
					ps.setString(2, discordUser.username());
					ps.executeUpdate();
				}
			});
			return true;
		} catch (Exception e) {
			logger.error("Failed to add/update special user", e);
			return false;
		}
	}

	/**
	 * Removes a special-user row by Discord snowflake.
	 *
	 * <p>The operation is idempotent; deleting a missing row is treated as success.
	 *
	 * @param userID the user to remove from the special-user table, must not be {@code null}
	 * @return {@code true} if the operation succeeds, {@code false} if a database error occurs
	 * @throws NullPointerException if {@code userID} is {@code null}
	 */
	public boolean removeSpecialUser(@NotNull UserID userID) {
		Objects.requireNonNull(userID, "userID must not be null");
		String sql = """
			DELETE FROM special_users
			WHERE user_id = ?
		""";

		try {
			database.transaction(conn -> {
				try (PreparedStatement ps = conn.prepareStatement(sql)) {
					ps.setLong(1, userID.value());
					ps.executeUpdate();
				}
			});
			return true;
		} catch (Exception e) {
			logger.error("Failed to remove special user", e);
			return false;
		}
	}


}
