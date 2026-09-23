package net.honeyberries.task;

import net.honeyberries.database.Database;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.List;

/**
 * Template-method base class for periodic maintenance tasks that share the same shape:
 * <ol>
 *     <li>log a start message,</li>
 *     <li>bail out early (with a warning) if the database isn't healthy,</li>
 *     <li>process a batch of items — in parallel — each producing a {@link TaskOutcome},</li>
 *     <li>tally the outcomes and log a summary (warn if any failures occurred, debug otherwise),</li>
 *     <li>catch and log any unexpected exception so the scheduler thread survives.</li>
 * </ol>
 * Subclasses only need to implement {@link #processItems()} to perform the actual per-item
 * work and {@link #itemUnitName()} to describe what's being counted in the summary log line.
 */
public abstract class AbstractScheduledTask implements Runnable {

    protected final Logger logger = LoggerFactory.getLogger(getClass());

    private final String taskName = getClass().getSimpleName();

    @Override
    public void run() {
        logger.debug("{} started", taskName);

        if (!Database.getInstance().isHealthy()) {
            logger.warn("Skipping {} because database is unavailable", taskName);
            return;
        }

        try {
            List<TaskOutcome> results = processItems();

            long updatedCount = results.stream().filter(outcome -> outcome == TaskOutcome.UPDATED).count();
            long skippedCount = results.stream().filter(outcome -> outcome == TaskOutcome.SKIPPED).count();
            long failedCount = results.stream().filter(outcome -> outcome == TaskOutcome.FAILED).count();

            if (failedCount > 0) {
                logger.warn("{} completed with {} updated, {} skipped, {} failed out of {} {}",
                        taskName, updatedCount, skippedCount, failedCount, results.size(), itemUnitName());
            } else {
                logger.debug("{} completed with {} updated and {} skipped out of {} {}",
                        taskName, updatedCount, skippedCount, results.size(), itemUnitName());
            }
        } catch (Exception e) {
            logger.error("Error in {}", taskName, e);
        }
    }

    /**
     * Performs the per-item work for this run and returns the outcome of each item processed.
     *
     * @return the list of outcomes for all items processed in this run; never {@code null}
     */
    protected abstract List<TaskOutcome> processItems();

    /**
     * @return the plural noun describing what's being counted in the summary log line
     *         (e.g. {@code "guilds"}, {@code "channels"})
     */
    protected abstract String itemUnitName();
}
