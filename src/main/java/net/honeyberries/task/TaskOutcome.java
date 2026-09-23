package net.honeyberries.task;

/**
 * Outcome of processing a single item (e.g. a guild or a channel) within a scheduled
 * maintenance task such as {@link GuildRulesTask} or {@link ChannelGuidelinesTask}.
 */
public enum TaskOutcome {
    UPDATED,
    SKIPPED,
    FAILED
}
