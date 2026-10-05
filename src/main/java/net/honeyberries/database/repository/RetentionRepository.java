package net.honeyberries.database.repository;

import org.jetbrains.annotations.NotNull;

/**
 * Repository for the data-retention purges run by {@code RetentionPurgeTask}.
 * Deletes or redacts stored moderation data once it is older than the configured retention window,
 * so the privacy policy's retention promises are enforced by code rather than by hand.
 */
public class RetentionRepository extends RepositoryBase {

	/** Singleton instance. */
	private static final RetentionRepository INSTANCE = new RetentionRepository();

	/**
	 * Retrieves the singleton instance of this repository.
	 *
	 * @return the singleton {@code RetentionRepository}
	 */
	@NotNull
	public static RetentionRepository getInstance() {
		return INSTANCE;
	}

	/**
	 * Constructs a new repository, retrieving the singleton database instance.
	 */
	public RetentionRepository() {
		super();
	}

	/**
	 * Deletes moderation actions created more than {@code days} days ago. Appeals, reversals and message
	 * deletions attached to a purged action are removed with it via {@code ON DELETE CASCADE}.
	 * <p>
	 * Actions are kept while they are still needed: an action with an open appeal is never purged, and
	 * neither is one whose temporary ban (duration in seconds) has not yet expired.
	 *
	 * @param days the retention window in days; must be positive
	 * @return the number of actions deleted, or {@code 0} if nothing matched or a database error occurred
	 * @throws IllegalArgumentException if {@code days} is not positive
	 */
	public int purgeActionsOlderThan(int days) {
		requirePositiveDays(days);

		String sql = """
			DELETE FROM guild_moderation_actions a
			WHERE a.created_at < now() - make_interval(days => ?)
			  AND NOT EXISTS (
			      SELECT 1 FROM moderation_appeals p
			      WHERE p.action_id = a.action_id AND p.is_open
			  )
			  AND (a.ban_duration <= 0
			       OR a.created_at + (a.ban_duration * INTERVAL '1 second') < now())
		""";

		return safeExecuteUpdate(conn -> {
			try (var ps = conn.prepareStatement(sql)) {
				ps.setInt(1, days);
				return ps.executeUpdate();
			}
		}, "Failed to purge moderation actions older than {} days", days);
	}

	/**
	 * Redacts the free text (the user's reason and the moderator's resolution note) of appeals that were
	 * resolved more than {@code days} days ago. The row itself and its outcome are kept; only the words
	 * are removed. Open appeals and already-redacted appeals are left alone.
	 *
	 * @param days the retention window in days, counted from when the appeal was resolved; must be positive
	 * @return the number of appeals redacted, or {@code 0} if nothing matched or a database error occurred
	 * @throws IllegalArgumentException if {@code days} is not positive
	 */
	public int clearResolvedAppealTextOlderThan(int days) {
		requirePositiveDays(days);

		String sql = """
			UPDATE moderation_appeals
			SET reason = '',
			    resolution_note = NULL
			WHERE NOT is_open
			  AND resolved_at < now() - make_interval(days => ?)
			  AND (reason <> '' OR resolution_note IS NOT NULL)
		""";

		return safeExecuteUpdate(conn -> {
			try (var ps = conn.prepareStatement(sql)) {
				ps.setInt(1, days);
				return ps.executeUpdate();
			}
		}, "Failed to redact resolved appeal text older than {} days", days);
	}

	private static void requirePositiveDays(int days) {
		if (days < 1) {
			throw new IllegalArgumentException("days must be positive, got " + days);
		}
	}
}
