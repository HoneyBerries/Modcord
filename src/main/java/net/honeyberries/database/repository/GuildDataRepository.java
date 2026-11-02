package net.honeyberries.database.repository;

import net.honeyberries.datatypes.discord.GuildID;
import org.jetbrains.annotations.NotNull;

import java.util.List;
import java.util.Objects;

/**
 * Removes every row the bot has stored for a guild, used when the bot leaves (or is removed from) a guild.
 * <p>
 * All guild-scoped tables reference {@code guild_preferences} with {@code ON DELETE CASCADE}, so deleting the
 * preferences row alone would already cascade. The explicit child-first order here is deliberate defence in
 * depth: it keeps the purge correct even if a cascade is ever dropped.
 * {@code special_users} is global (keyed by user id only) and is intentionally left untouched.
 */
public class GuildDataRepository extends RepositoryBase {

	private static final GuildDataRepository INSTANCE = new GuildDataRepository();

	/** Delete statements in dependency order (children first); each takes the guild id as its only parameter. */
	private static final List<String> PURGE_STATEMENTS = List.of(
			"DELETE FROM guild_moderation_action_deletions WHERE action_id IN (SELECT action_id FROM guild_moderation_actions WHERE guild_id = ?)",
			"DELETE FROM guild_moderation_action_reversals WHERE action_id IN (SELECT action_id FROM guild_moderation_actions WHERE guild_id = ?)",
			"DELETE FROM moderation_appeals WHERE guild_id = ?",
			"DELETE FROM guild_moderation_actions WHERE guild_id = ?",
			"DELETE FROM guild_moderation_exemptions WHERE guild_id = ?",
			"DELETE FROM guild_channel_guidelines WHERE guild_id = ?",
			"DELETE FROM guild_rules WHERE guild_id = ?",
			"DELETE FROM guild_preferences WHERE guild_id = ?"
	);

	@NotNull
	public static GuildDataRepository getInstance() {
		return INSTANCE;
	}

	public GuildDataRepository() {
		super();
	}

	/**
	 * Deletes all stored data for the guild in a single transaction. Either everything is removed or nothing is.
	 *
	 * @param guildId the guild to purge
	 * @return {@code true} if the purge committed (including when there was nothing to delete), {@code false} on a database error
	 * @throws NullPointerException if {@code guildId} is {@code null}
	 */
	public boolean purgeGuildData(@NotNull GuildID guildId) {
		Objects.requireNonNull(guildId, "guildId must not be null");

		boolean ok = safeTransaction(conn -> {
			for (String sql : PURGE_STATEMENTS) {
				try (var ps = conn.prepareStatement(sql)) {
					ps.setLong(1, guildId.value());
					ps.executeUpdate();
				}
			}
		}, "Failed to purge stored data for guild " + guildId.value());

		if (ok) {
			logger.info("Purged all stored data for guild {}", guildId.value());
		}
		return ok;
	}
}
