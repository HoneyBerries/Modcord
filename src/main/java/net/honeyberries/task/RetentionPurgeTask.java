package net.honeyberries.task;

import net.honeyberries.config.AppConfig;
import net.honeyberries.database.repository.RetentionRepository;

import java.util.List;

/**
 * Daily maintenance task that enforces the data-retention windows from {@code app_config.yml}:
 * <ol>
 *     <li>deletes moderation actions (and their appeals, reversals and deletions) past the actions window,</li>
 *     <li>redacts the free text of resolved appeals past the appeal-text window.</li>
 * </ol>
 * Only counts are logged, never any stored content.
 */
public class RetentionPurgeTask extends AbstractScheduledTask {

    private final RetentionRepository retentionRepository = RetentionRepository.getInstance();

    /**
     * Processes the retention rules configured in the application by performing two operations:
     * <p>
     * 1. Purges moderation actions that are older than the configured retention period, along with their
     *    associated appeals, reversals, and deletions.
     * <p>
     * 2. Redacts the free text of resolved appeals that are older than the configured retention period.
     * <p>
     * Moderation actions with open appeals or unexpired temporary bans are not purged.
     * Appeals that are still open or already redacted are not modified.
     * <p>
     * Logs the number of moderation actions purged and resolved appeals redacted, if any.
     *
     * @return a list of {@link TaskOutcome} results for each operation:
     *         - The first element indicates whether any moderation actions were purged.
     *         - The second element indicates whether any resolved appeals were redacted.
     *         {@code UPDATED} if changes were made, {@code SKIPPED} if no changes were needed.
     */
    @Override
    protected List<TaskOutcome> processItems() {
        AppConfig config = AppConfig.getInstance();

        int purgedActions = retentionRepository.purgeActionsOlderThan(config.getActionRetentionDays());
        int redactedAppeals = retentionRepository.clearResolvedAppealTextOlderThan(config.getAppealTextRetentionDays());

        if (purgedActions > 0 || redactedAppeals > 0) {
            logger.info("Retention purge removed {} moderation actions and redacted {} resolved appeals",
                    purgedActions, redactedAppeals);
        }

        return List.of(
                purgedActions > 0 ? TaskOutcome.UPDATED : TaskOutcome.SKIPPED,
                redactedAppeals > 0 ? TaskOutcome.UPDATED : TaskOutcome.SKIPPED
        );
    }

    @Override
    protected String itemUnitName() {
        return "retention steps";
    }
}
