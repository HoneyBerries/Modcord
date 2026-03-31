package net.honeyberries.task;

import net.honeyberries.database.Database;
import net.honeyberries.database.GuildModerationActionRepository;
import net.honeyberries.datatypes.action.ActionData;
import net.honeyberries.datatypes.action.ActionType;
import net.honeyberries.datatypes.discord.GuildID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

public class UnbanWatcherTask implements Runnable {

    private static final Logger logger = LoggerFactory.getLogger(UnbanWatcherTask.class);
    private final GuildModerationActionRepository actionRepository = GuildModerationActionRepository.getInstance();
    private final Database database = Database.getInstance();

    @Override
    public void run() {
        logger.debug("UnbanWatcherTask started");

        try {
            List<GuildID> guildIds = getAllGuildIdsWithBans();

            for (GuildID guildId : guildIds) {
                processBansForGuild(guildId);
            }

            logger.debug("UnbanWatcherTask completed");
        } catch (Exception e) {
            logger.error("Error in UnbanWatcherTask", e);
        }
    }

    private List<GuildID> getAllGuildIdsWithBans() {
        String sql = """
            SELECT DISTINCT guild_id
            FROM guild_moderation_actions
            WHERE action = ?
        """;

        try {
            return database.query(conn -> {
                List<GuildID> guildIds = new ArrayList<>();

                try (PreparedStatement ps = conn.prepareStatement(sql)) {
                    ps.setString(1, ActionType.BAN.name());

                    try (ResultSet rs = ps.executeQuery()) {
                        while (rs.next()) {
                            guildIds.add(new GuildID(rs.getLong("guild_id")));
                        }
                    }
                }

                return guildIds;
            });
        } catch (Exception e) {
            logger.error("Failed to fetch guild IDs with bans", e);
            return List.of();
        }
    }

    private void processBansForGuild(GuildID guildId) {
        try {
            List<ActionData> banActions = actionRepository.getActionsByGuild(guildId)
                    .stream()
                    .filter(a -> a.action() == ActionType.BAN)
                    .toList();

            for (ActionData action : banActions) {
                if (isBanExpired(action)) {
                    logger.info("Ban expired for user {} in guild {}, unbanning...", action.userId(), guildId);

                    // TODO: Implement actual Discord unban logic
                    // 1. Get the Guild object from JDA
                    // 2. Unban the user using guild.unban(userId).queue()
                    // 3. Handle the response/errors appropriately

                    logger.debug("TODO: Unban user {} in guild {}", action.userId(), guildId);
                }
            }
        } catch (Exception e) {
            logger.error("Error processing bans for guild {}", guildId, e);
        }
    }

    private boolean isBanExpired(ActionData action) {
        // Permanent ban (duration -1) never expires
        if (action.banDuration() == 2147483647L) {
            return false;
        }

        // Get the creation timestamp from the database for this action
        Long createdAtMillis = getActionCreatedTimestamp(action.id());
        if (createdAtMillis == null) {
            logger.warn("Could not find creation timestamp for action {}", action.id());
            return false;
        }

        // Calculate expiration time: creation_time + ban_duration (in seconds)
        long expirationTime = createdAtMillis + (action.banDuration() * 1000L);
        return System.currentTimeMillis() >= expirationTime;
    }

    private Long getActionCreatedTimestamp(UUID actionId) {
        String sql = """
            SELECT created_at
            FROM guild_moderation_actions
            WHERE id = ?
        """;

        try {
            return database.query(conn -> {
                try (PreparedStatement ps = conn.prepareStatement(sql)) {
                    ps.setObject(1, actionId);

                    try (ResultSet rs = ps.executeQuery()) {
                        if (rs.next()) {
                            java.sql.Timestamp createdAt = rs.getTimestamp("created_at");
                            if (createdAt != null) {
                                return createdAt.getTime();
                            }
                        }
                    }
                }
                return null;
            });
        } catch (Exception e) {
            logger.error("Failed to fetch creation timestamp for action {}", actionId, e);
            return null;
        }
    }
}