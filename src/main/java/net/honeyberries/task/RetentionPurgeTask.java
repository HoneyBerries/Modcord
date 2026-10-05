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
