package net.honeyberries.database;

import net.honeyberries.datatypes.discord.ChannelID;
import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.discord.RoleID;
import net.honeyberries.datatypes.discord.UserID;
import org.jetbrains.annotations.NotNull;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

/**
 * Repository for moderation exemptions stored in {@code guild_moderation_exemptions}.
 * Manages user, role, and channel-level exemptions from automated moderation in guild contexts.
 * Exemptions prevent AI detection, auto-moderation actions, and other automated systems from targeting specific users, roles, or channels.
 */
public class ExcludedEntitiesRepository {

    /**
     * Immutable view of exclusions for a single guild.
     *
     * @param userIDs excluded users in the guild, never {@code null}
     * @param roleIDs excluded roles in the guild, never {@code null}
     * @param channelIDs excluded channels in the guild, never {@code null}
     */
    public record ExcludedEntities(@NotNull List<UserID> userIDs, @NotNull List<RoleID> roleIDs, @NotNull List<ChannelID> channelIDs) {}

    private final Database database;
    private final Logger logger = LoggerFactory.getLogger(ExcludedEntitiesRepository.class);

    private static final ExcludedEntitiesRepository INSTANCE = new ExcludedEntitiesRepository();


    /**
     * Creates a repository instance backed by the shared {@link Database} singleton.
     */
    private ExcludedEntitiesRepository() {
        this.database = Database.getInstance();
    }

    /**
     * Returns the shared repository instance.
     *
     * @return the singleton {@code ExcludedEntitiesRepository}
     */
    @NotNull
    public static ExcludedEntitiesRepository getInstance() {
        return INSTANCE;
    }

    /**
     * Checks whether a user is exempt from moderation automation in a guild.
     *
     * @param guildID the guild to check, must not be {@code null}
     * @param userID the user to check, must not be {@code null}
     * @return {@code true} when an exemption row exists, {@code false} otherwise or if a database error occurs
     * @throws NullPointerException if {@code guildID} or {@code userID} is {@code null}
     */
    public boolean isExcluded(@NotNull GuildID guildID, @NotNull UserID userID) {
        Objects.requireNonNull(guildID, "guildID must not be null");
        Objects.requireNonNull(userID, "userID must not be null");
        String sql = """
            SELECT 1
            FROM guild_moderation_exemptions
            WHERE guild_id = ? AND user_id = ? AND role_id IS NULL
            LIMIT 1
        """;

        try {
            return database.query(conn -> {
                try (PreparedStatement ps = conn.prepareStatement(sql)) {
                    ps.setLong(1, guildID.value());
                    ps.setLong(2, userID.value());

                    try (ResultSet rs = ps.executeQuery()) {
                        return rs.next();
                    }
                }
            });
        } catch (Exception e) {
            logger.error("Failed to check excluded user", e);
            return false;
        }
    }

    /**
     * Checks whether a role is exempt from moderation automation in a guild.
     *
     * @param guildID the guild to check, must not be {@code null}
     * @param roleID the role to check, must not be {@code null}
     * @return {@code true} when an exemption row exists, {@code false} otherwise or if a database error occurs
     * @throws NullPointerException if {@code guildID} or {@code roleID} is {@code null}
     */
    public boolean isExcluded(@NotNull GuildID guildID, @NotNull RoleID roleID) {
        Objects.requireNonNull(guildID, "guildID must not be null");
        Objects.requireNonNull(roleID, "roleID must not be null");
        String sql = """
            SELECT 1
            FROM guild_moderation_exemptions
            WHERE guild_id = ? AND role_id = ? AND user_id IS NULL
            LIMIT 1
        """;

        try {
            return database.query(conn -> {
                try (PreparedStatement ps = conn.prepareStatement(sql)) {
                    ps.setLong(1, guildID.value());
                    ps.setLong(2, roleID.value());

                    try (ResultSet rs = ps.executeQuery()) {
                        return rs.next();
                    }
                }
            });
        } catch (Exception e) {
            logger.error("Failed to check excluded role", e);
            return false;
        }
    }

    /**
     * Checks whether a channel is exempt from moderation automation in a guild.
     *
     * @param guildID the guild to check, must not be {@code null}
     * @param channelID the channel to check, must not be {@code null}
     * @return {@code true} when an exemption row exists, {@code false} otherwise or if a database error occurs
     * @throws NullPointerException if {@code guildID} or {@code channelID} is {@code null}
     */
    public boolean isExcluded(@NotNull GuildID guildID, @NotNull ChannelID channelID) {
        Objects.requireNonNull(guildID, "guildID must not be null");
        Objects.requireNonNull(channelID, "channelID must not be null");
        String sql = """
            SELECT 1
            FROM guild_moderation_exemptions
            WHERE guild_id = ? AND channel_id = ? AND user_id IS NULL AND role_id IS NULL
            LIMIT 1
        """;

        try {
            return database.query(conn -> {
                try (PreparedStatement ps = conn.prepareStatement(sql)) {
                    ps.setLong(1, guildID.value());
                    ps.setLong(2, channelID.value());

                    try (ResultSet rs = ps.executeQuery()) {
                        return rs.next();
                    }
                }
            });
        } catch (Exception e) {
            logger.error("Failed to check excluded channel", e);
            return false;
        }
    }


    /**
     * Marks a user as exempt from moderation automation in a guild.
     *
     * <p>The operation is idempotent; existing rows are left unchanged.
     *
     * @param guildID the guild where the exemption applies, must not be {@code null}
     * @param userID the user to exempt, must not be {@code null}
     * @return {@code true} when the operation completes without error, {@code false} if a database error occurs
     * @throws NullPointerException if {@code guildID} or {@code userID} is {@code null}
     */
    public boolean markExcluded(@NotNull GuildID guildID, @NotNull UserID userID) {
        Objects.requireNonNull(guildID, "guildID must not be null");
        Objects.requireNonNull(userID, "userID must not be null");
        String sql = """
            INSERT INTO guild_moderation_exemptions (guild_id, user_id, role_id)
            VALUES (?, ?, NULL)
            ON CONFLICT (guild_id, user_id) WHERE user_id IS NOT NULL DO NOTHING
        """;

        try {
            database.transaction(conn -> {
                try (PreparedStatement ps = conn.prepareStatement(sql)) {
                    ps.setLong(1, guildID.value());
                    ps.setLong(2, userID.value());
                    ps.executeUpdate();
                }
            });
            return true;
        } catch (Exception e) {
            logger.error("Failed to mark user as excluded", e);
            return false;
        }
    }


    /**
     * Marks a role as exempt from moderation automation in a guild.
     *
     * <p>The operation is idempotent; existing rows are left unchanged.
     *
     * @param guildID the guild where the exemption applies, must not be {@code null}
     * @param roleID the role to exempt, must not be {@code null}
     * @return {@code true} when the operation completes without error, {@code false} if a database error occurs
     * @throws NullPointerException if {@code guildID} or {@code roleID} is {@code null}
     */
    public boolean markExcluded(@NotNull GuildID guildID, @NotNull RoleID roleID) {
        Objects.requireNonNull(guildID, "guildID must not be null");
        Objects.requireNonNull(roleID, "roleID must not be null");
        String sql = """
            INSERT INTO guild_moderation_exemptions (guild_id, user_id, role_id)
            VALUES (?, NULL, ?)
            ON CONFLICT (guild_id, role_id) WHERE role_id IS NOT NULL DO NOTHING
        """;

        try {
            database.transaction(conn -> {
                try (PreparedStatement ps = conn.prepareStatement(sql)) {
                    ps.setLong(1, guildID.value());
                    ps.setLong(2, roleID.value());
                    ps.executeUpdate();
                }
            });
            return true;
        } catch (Exception e) {
            logger.error("Failed to mark role as excluded", e);
            return false;
        }
    }

    /**
     * Marks a channel as exempt from moderation automation in a guild.
     *
     * <p>The operation is idempotent; existing rows are left unchanged.
     *
     * @param guildID the guild where the exemption applies, must not be {@code null}
     * @param channelID the channel to exempt, must not be {@code null}
     * @return {@code true} when the operation completes without error, {@code false} if a database error occurs
     * @throws NullPointerException if {@code guildID} or {@code channelID} is {@code null}
     */
    public boolean markExcluded(@NotNull GuildID guildID, @NotNull ChannelID channelID) {
        Objects.requireNonNull(guildID, "guildID must not be null");
        Objects.requireNonNull(channelID, "channelID must not be null");
        String sql = """
            INSERT INTO guild_moderation_exemptions (guild_id, user_id, role_id, channel_id)
            VALUES (?, NULL, NULL, ?)
            ON CONFLICT (guild_id, channel_id) WHERE channel_id IS NOT NULL DO NOTHING
        """;

        try {
            database.transaction(conn -> {
                try (PreparedStatement ps = conn.prepareStatement(sql)) {
                    ps.setLong(1, guildID.value());
                    ps.setLong(2, channelID.value());
                    ps.executeUpdate();
                }
            });
            return true;
        } catch (Exception e) {
            logger.error("Failed to mark channel as excluded", e);
            return false;
        }
    }

    /**
     * Removes a user moderation exemption in a guild.
     *
     * <p>The operation is idempotent; removing a missing row is treated as success.
     *
     * @param guildID the guild where the exemption applies, must not be {@code null}
     * @param userID the user to un-exempt, must not be {@code null}
     * @return {@code true} when the operation completes without error, {@code false} if a database error occurs
     * @throws NullPointerException if {@code guildID} or {@code userID} is {@code null}
     */
    public boolean unmarkExcluded(@NotNull GuildID guildID, @NotNull UserID userID) {
        Objects.requireNonNull(guildID, "guildID must not be null");
        Objects.requireNonNull(userID, "userID must not be null");
        String sql = """
            DELETE FROM guild_moderation_exemptions
            WHERE guild_id = ? AND user_id = ? AND role_id IS NULL
        """;

        try {
            database.transaction(conn -> {
                try (PreparedStatement ps = conn.prepareStatement(sql)) {
                    ps.setLong(1, guildID.value());
                    ps.setLong(2, userID.value());
                    ps.executeUpdate();
                }
            });
            return true;
        } catch (Exception e) {
            logger.error("Failed to unmark excluded user", e);
            return false;
        }
    }

    /**
     * Removes a role moderation exemption in a guild.
     *
     * <p>The operation is idempotent; removing a missing row is treated as success.
     *
     * @param guildID the guild where the exemption applies, must not be {@code null}
     * @param roleID the role to un-exempt, must not be {@code null}
     * @return {@code true} when the operation completes without error, {@code false} if a database error occurs
     * @throws NullPointerException if {@code guildID} or {@code roleID} is {@code null}
     */
    public boolean unmarkExcluded(@NotNull GuildID guildID, @NotNull RoleID roleID) {
        Objects.requireNonNull(guildID, "guildID must not be null");
        Objects.requireNonNull(roleID, "roleID must not be null");
        String sql = """
            DELETE FROM guild_moderation_exemptions
            WHERE guild_id = ? AND role_id = ? AND user_id IS NULL
        """;

        try {
            database.transaction(conn -> {
                try (PreparedStatement ps = conn.prepareStatement(sql)) {
                    ps.setLong(1, guildID.value());
                    ps.setLong(2, roleID.value());
                    ps.executeUpdate();
                }
            });
            return true;
        } catch (Exception e) {
            logger.error("Failed to unmark excluded role", e);
            return false;
        }
    }

    /**
     * Removes a channel moderation exemption in a guild.
     *
     * <p>The operation is idempotent; removing a missing row is treated as success.
     *
     * @param guildID the guild where the exemption applies, must not be {@code null}
     * @param channelID the channel to un-exempt, must not be {@code null}
     * @return {@code true} when the operation completes without error, {@code false} if a database error occurs
     * @throws NullPointerException if {@code guildID} or {@code channelID} is {@code null}
     */
    public boolean unmarkExcluded(@NotNull GuildID guildID, @NotNull ChannelID channelID) {
        Objects.requireNonNull(guildID, "guildID must not be null");
        Objects.requireNonNull(channelID, "channelID must not be null");
        String sql = """
            DELETE FROM guild_moderation_exemptions
            WHERE guild_id = ? AND channel_id = ? AND user_id IS NULL AND role_id IS NULL
        """;

        try {
            database.transaction(conn -> {
                try (PreparedStatement ps = conn.prepareStatement(sql)) {
                    ps.setLong(1, guildID.value());
                    ps.setLong(2, channelID.value());
                    ps.executeUpdate();
                }
            });
            return true;
        } catch (Exception e) {
            logger.error("Failed to unmark excluded channel", e);
            return false;
        }
    }

    /**
     * Returns all excluded users, roles, and channels configured for the provided guild.
     *
     * <p>Rows are partitioned into user, role, and channel lists based on which target column is populated.
     * The result is safe to use for read-only display logic such as slash-command listings.
     *
     * @param guildID the guild scope to fetch exclusions for, must not be {@code null}
     * @return an immutable snapshot of excluded users, roles, and channels, never {@code null}; empty lists when none are configured
     * @throws NullPointerException if {@code guildID} is {@code null}
     */
    @NotNull
    public ExcludedEntities getExcludedEntities(@NotNull GuildID guildID) {
        Objects.requireNonNull(guildID, "guildID must not be null");
        String sql = """
            SELECT user_id, role_id, channel_id
            FROM guild_moderation_exemptions
            WHERE guild_id = ?
            ORDER BY created_at
        """;

        try {
            return database.query(conn -> {
                List<UserID> userIDs = new ArrayList<>();
                List<RoleID> roleIDs = new ArrayList<>();
                List<ChannelID> channelIDs = new ArrayList<>();

                try (PreparedStatement ps = conn.prepareStatement(sql)) {
                    ps.setLong(1, guildID.value());

                    try (ResultSet rs = ps.executeQuery()) {
                        while (rs.next()) {
                            long userIdRaw = rs.getLong("user_id");
                            if (!rs.wasNull()) {
                                userIDs.add(new UserID(userIdRaw));
                                continue;
                            }

                            long roleIdRaw = rs.getLong("role_id");
                            if (!rs.wasNull()) {
                                roleIDs.add(new RoleID(roleIdRaw));
                                continue;
                            }

                            long channelIdRaw = rs.getLong("channel_id");
                            if (!rs.wasNull()) {
                                channelIDs.add(new ChannelID(channelIdRaw));
                            }
                        }
                    }
                }

                return new ExcludedEntities(List.copyOf(userIDs), List.copyOf(roleIDs), List.copyOf(channelIDs));
            });
        } catch (Exception e) {
            logger.error("Failed to fetch excluded users, roles, and channels", e);
            return new ExcludedEntities(List.of(), List.of(), List.of());
        }
    }

}
