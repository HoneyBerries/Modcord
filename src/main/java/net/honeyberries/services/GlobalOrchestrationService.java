package net.honeyberries.services;

import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.Message;
import net.honeyberries.config.AppConfig;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.discord.MessageID;
import org.jetbrains.annotations.NotNull;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.*;
import java.util.concurrent.*;

/**
 * Manages per-guild moderation message processing pipelines and coordinates scheduled batch processing.
 * Acts as the global coordinator for all guild message queues, scheduling AI-based moderation inference
 * runs on a configurable delay after each message arrival. Handles lifecycle management of individual
 * {@code GuildMessageProcessingService} instances and prevents duplicate processing via in-flight tracking.
 * <p>
 * Responsibilities:
 * - Maintain per-guild message queues and processing services
 * - Schedule delayed processing runs when messages arrive
 * - Prevent concurrent processing of the same guild (in-flight tracking)
 * - Graceful shutdown with cleanup of pending runs and queues
 */
public class GlobalOrchestrationService {

    /** Logger for orchestration events and guild processing lifecycle. */
    private final Logger logger = LoggerFactory.getLogger(GlobalOrchestrationService.class);

    /** Singleton instance. */
    private static final GlobalOrchestrationService INSTANCE = new GlobalOrchestrationService();
    
    /** Per-guild message processing services, lazily created on first message. */
    private final Map<GuildID, GuildMessageProcessingService> guildServices = new ConcurrentHashMap<>();
    
    /** Pending scheduled processing runs, keyed by guild ID. */
    private final Map<GuildID, ScheduledFuture<?>> scheduledGuildRuns = new ConcurrentHashMap<>();
    
    /** In-flight guild processing operations to prevent concurrent runs. */
    private final Set<GuildID> guildsInFlight = ConcurrentHashMap.newKeySet();
    
    /** Shared thread pool for scheduling guild processing runs (4 threads for batching). */
    private final ScheduledExecutorService scheduler = Executors.newScheduledThreadPool(4);

    private GlobalOrchestrationService() {}

    /**
     * Retrieves the singleton instance of the orchestration service.
     *
     * @return the singleton {@code GlobalOrchestrationService}
     */
    @NotNull
    public static GlobalOrchestrationService getInstance() {
        return INSTANCE;
    }

    /**
     * Adds a message to the guild's message queue and schedules a processing run.
     * If a processing run is already scheduled for this guild, it is cancelled and rescheduled
     * from this moment with a fresh delay. This coalesces rapid message arrivals into a single run.
     *
     * @param guild the Discord guild (must not be {@code null})
     * @param message the Discord message to add (must not be {@code null})
     * @param isHistory {@code true} if this is historical context, {@code false} if current message
     * @throws NullPointerException if {@code guild} or {@code message} is {@code null}
     */
    public void addMessage(@NotNull Guild guild, @NotNull Message message, boolean isHistory) {
        Objects.requireNonNull(guild, "guild must not be null");
        Objects.requireNonNull(message, "message must not be null");
        
        GuildID guildId = GuildID.fromGuild(guild);
        getOrCreate(guild).addMessage(message, isHistory);
        scheduleGuildRun(guild, guildId);
    }

    /**
     * Updates a message in the guild's queue and reschedules processing.
     * If the message already exists, it is replaced with the new content.
     * Scheduling follows the same coalescing logic as {@code addMessage()}.
     *
     * @param guild the Discord guild (must not be {@code null})
     * @param message the updated Discord message (must not be {@code null})
     * @param isHistory {@code true} if this is historical context
     * @throws NullPointerException if {@code guild} or {@code message} is {@code null}
     */
    public void updateMessage(@NotNull Guild guild, @NotNull Message message, boolean isHistory) {
        Objects.requireNonNull(guild, "guild must not be null");
        Objects.requireNonNull(message, "message must not be null");
        
        GuildID guildId = GuildID.fromGuild(guild);
        getOrCreate(guild).updateMessage(message, isHistory);
        scheduleGuildRun(guild, guildId);
    }

    /**
     * Removes a message from the guild's queue.
     * If a processing run is already in-flight, removal is logged but no cancellation occurs.
     * If the queue becomes empty after removal, any pending scheduled run is cancelled.
     *
     * @param guild the Discord guild (must not be {@code null})
     * @param messageId the ID of the message to remove (must not be {@code null})
     * @throws NullPointerException if {@code guild} or {@code messageId} is {@code null}
     */
    public void removeMessage(@NotNull Guild guild, @NotNull MessageID messageId) {
        Objects.requireNonNull(guild, "guild must not be null");
        Objects.requireNonNull(messageId, "messageId must not be null");
        
        GuildID guildId = GuildID.fromGuild(guild);
        GuildMessageProcessingService service = getOrCreate(guild);
        service.removeMessage(messageId);

        // If the run is already in-flight, there is nothing left to cancel.
        if (guildsInFlight.contains(guildId)) {
            return;
        }

        if (service.isQueueEmpty()) {
            ScheduledFuture<?> scheduledRun = scheduledGuildRuns.remove(guildId);
            if (scheduledRun != null) {
                scheduledRun.cancel(false);
                logger.debug("Canceled pending processing for guild {} because queue is now empty", guildId.value());
            }
        }
    }

    /**
     * Executes the full moderation processing pipeline for a guild.
     * Marks the guild as in-flight to prevent concurrent processing, executes the pipeline,
     * and handles all exceptions gracefully with logging. Automatically removes the guild from in-flight
     * status in the finally block regardless of success or failure.
     *
     * @param guild the Discord guild to process (must not be {@code null})
     * @throws NullPointerException if {@code guild} is {@code null}
     */
    public void processGuild(@NotNull Guild guild) {
        Objects.requireNonNull(guild, "guild must not be null");
        
        GuildID guildId = GuildID.fromGuild(guild);
        scheduledGuildRuns.remove(guildId);

        // Add to in-flight set; if already present, skip processing (duplicate in-flight)
        if (!guildsInFlight.add(guildId)) {
            return;
        }

        try {
            GuildMessageProcessingService service = getOrCreate(guild);
            if (service.isQueueEmpty()) {
                logger.debug("Skipping processing for guild {} because queue is empty", guildId.value());
                return;
            }

            logger.info("Triggering processing for guild {}", guild.getId());
            boolean success = service.runPipeline();
            if (!success) {
                logger.warn("Guild {} processing produced no actionable results", guild.getId());
            }
        } catch (Exception e) {
            logger.error("Unhandled failure while processing guild {}", guild.getId(), e);
        } finally {
            guildsInFlight.remove(guildId);
        }
    }

    /**
     * Initiates graceful shutdown of all processing services.
     * Cancels all pending scheduled runs without waiting (cancel(false)) and clears the queue
     * for all guilds. Then shuts down the scheduler immediately without waiting for running tasks.
     * Called during bot shutdown to ensure no stray processing continues.
     */
    public void shutdownNowAndDropPending() {
        scheduledGuildRuns.values().forEach(future -> future.cancel(false));
        scheduledGuildRuns.clear();
        guildServices.values().forEach(GuildMessageProcessingService::clearQueue);
        scheduler.shutdownNow();
    }

    /**
     * Schedules a delayed processing run for a guild, replacing any previous scheduled run.
     * Calculates the delay in milliseconds from {@code AppConfig.getModerationQueueDuration()},
     * ensures a minimum delay of 1 millisecond, and schedules the run on the executor.
     *
     * @param guild the Discord guild (must not be {@code null})
     * @param guildId the guild's ID (must not be {@code null})
     * @throws NullPointerException if {@code guild} or {@code guildId} is {@code null}
     */
    private void scheduleGuildRun(@NotNull Guild guild, @NotNull GuildID guildId) {
        Objects.requireNonNull(guild, "guild must not be null");
        Objects.requireNonNull(guildId, "guildId must not be null");
        
        ScheduledFuture<?> previous = scheduledGuildRuns.remove(guildId);
        if (previous != null) {
            previous.cancel(false);
        }

        long delayMillis = Math.round(AppConfig.getInstance().getModerationQueueDuration() * 1000.0);
        long safeDelayMillis = Math.max(1L, delayMillis);

        ScheduledFuture<?> next = scheduler.schedule(
                () -> processGuild(guild),
                safeDelayMillis,
                TimeUnit.MILLISECONDS
        );
        scheduledGuildRuns.put(guildId, next);
    }

    /**
     * Retrieves or lazily creates the message processing service for a guild.
     * If no service exists, a new {@code GuildMessageProcessingService} is instantiated.
     *
     * @param guild the Discord guild (must not be {@code null})
     * @return the guild's message processing service
     * @throws NullPointerException if {@code guild} is {@code null}
     */
    @NotNull
    private GuildMessageProcessingService getOrCreate(@NotNull Guild guild) {
        Objects.requireNonNull(guild, "guild must not be null");
        
        return guildServices.computeIfAbsent(
                GuildID.fromGuild(guild),
                id -> new GuildMessageProcessingService(guild)
        );
    }
}