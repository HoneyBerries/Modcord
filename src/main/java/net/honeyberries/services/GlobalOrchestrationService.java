package net.honeyberries.services;

import net.dv8tion.jda.api.entities.Guild;
import net.dv8tion.jda.api.entities.Message;
import net.honeyberries.config.AppConfig;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.discord.MessageID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.Map;
import java.util.Set;
import java.util.concurrent.*;

public class GlobalOrchestrationService {

    private final Logger logger = LoggerFactory.getLogger(GlobalOrchestrationService.class);

    private static final GlobalOrchestrationService INSTANCE = new GlobalOrchestrationService();
    private final Map<GuildID, GuildMessageProcessingService> guildServices = new ConcurrentHashMap<>();
    private final Map<GuildID, ScheduledFuture<?>> scheduledGuildRuns = new ConcurrentHashMap<>();
    private final Set<GuildID> guildsInFlight = ConcurrentHashMap.newKeySet();
    private final ScheduledExecutorService scheduler = Executors.newScheduledThreadPool(4);

    private GlobalOrchestrationService() {}

    public static GlobalOrchestrationService getInstance() {
        return INSTANCE;
    }

    public void addMessage(Guild guild, Message message, boolean isHistory) {
        GuildID guildId = GuildID.fromGuild(guild);
        getOrCreate(guild).addMessage(message, isHistory);
        scheduleGuildRun(guild, guildId);
    }

    public void updateMessage(Guild guild, Message message, boolean isHistory) {
        GuildID guildId = GuildID.fromGuild(guild);
        getOrCreate(guild).updateMessage(message, isHistory);
        scheduleGuildRun(guild, guildId);
    }

    public void removeMessage(Guild guild, MessageID messageId) {
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

    public void processGuild(Guild guild) {
        GuildID guildId = GuildID.fromGuild(guild);
        scheduledGuildRuns.remove(guildId);

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

    public void shutdownNowAndDropPending() {
        scheduledGuildRuns.values().forEach(future -> future.cancel(false));
        scheduledGuildRuns.clear();
        guildServices.values().forEach(GuildMessageProcessingService::clearQueue);
        scheduler.shutdownNow();
    }

    private void scheduleGuildRun(Guild guild, GuildID guildId) {
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

    private GuildMessageProcessingService getOrCreate(Guild guild) {
        return guildServices.computeIfAbsent(
                GuildID.fromGuild(guild),
                id -> new GuildMessageProcessingService(guild)
        );
    }
}