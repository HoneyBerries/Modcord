package net.honeyberries.database;

import net.honeyberries.datatypes.discord.GuildID;
import net.honeyberries.datatypes.discord.RoleID;
import net.honeyberries.datatypes.discord.UserID;
import org.jetbrains.annotations.NotNull;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

/**
 * Repository for moderation exemptions stored in {@code guild_moderation_exemptions}.
 *
 * <p>Each exemption is scoped by guild and can target either a user or a role.
 */
public class ExcludedUsersRepository {

    /**
     * Immutable view of exclusions for a single guild.
     *
     * @param userIDs excluded users in the guild
     * @param roleIDs excluded roles in the guild
     */
    public record ExcludedEntities(@NotNull List<UserID> userIDs, @NotNull List<RoleID> roleIDs) {}

    private final Database database;
    private final Logger logger = LoggerFactory.getLogger(ExcludedUsersRepository.class);

    private static final ExcludedUsersRepository INSTANCE = new ExcludedUsersRepository();


    /**
     * Creates a repository instance backed by the shared {@link Database} singleton.
     */
    private ExcludedUsersRepository() {
        this.database = Database.getInstance();
    }

    /**
     * Returns the shared repository instance.
     *
     * @return singleton repository
     */
    public static ExcludedUsersRepository getInstance() {
        return INSTANCE;
    }

    /**
     * Checks whether a user is exempt from moderation automation in a guild.
     *
     * @param guildID guild to check
     * @param userID  user to check
     * @return {@code true} when an exemption row exists, otherwise {@code false}
     */
    public boolean isExcluded(@NotNull GuildID guildID, @NotNull UserID userID) {
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
     * @param guildID guild to check
     * @param roleID  role to check
     * @return {@code true} when an exemption row exists, otherwise {@code false}
     */
    public boolean isExcluded(@NotNull GuildID guildID, @NotNull RoleID roleID) {
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
     * Marks a user as exempt from moderation automation in a guild.
     *
     * <p>The operation is idempotent; existing rows are left unchanged.
     *
     * @param guildID guild where the exemption applies
     * @param userID  user to exempt
     * @return {@code true} when the operation completes without error, otherwise {@code false}
     */
    public boolean markExcluded(@NotNull GuildID guildID, @NotNull UserID userID) {
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
     * @param guildID guild where the exemption applies
     * @param roleID  role to exempt
     * @return {@code true} when the operation completes without error, otherwise {@code false}
     */
    public boolean markExcluded(@NotNull GuildID guildID, @NotNull RoleID roleID) {
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
     * Removes a user moderation exemption in a guild.
     *
     * <p>The operation is idempotent; removing a missing row is treated as success.
     *
     * @param guildID guild where the exemption applies
     * @param userID  user to un-exempt
     * @return {@code true} when the operation completes without error, otherwise {@code false}
     */
    public boolean unmarkExcluded(@NotNull GuildID guildID, @NotNull UserID userID) {
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
     * @param guildID guild where the exemption applies
     * @param roleID  role to un-exempt
     * @return {@code true} when the operation completes without error, otherwise {@code false}
     */
    public boolean unmarkExcluded(@NotNull GuildID guildID, @NotNull RoleID roleID) {
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
     * Returns all excluded users and roles configured for the provided guild.
     *
     * <p>Rows are partitioned into user and role lists based on which target column is populated.
     * The result is safe to use for read-only display logic such as slash-command listings.
     *
     * @param guildID guild scope to fetch exclusions for
     * @return immutable snapshot of excluded users and roles; empty lists when none are configured
     */
    @NotNull
    public ExcludedEntities getExcludedEntities(@NotNull GuildID guildID) {
        String sql = """
            SELECT user_id, role_id
            FROM guild_moderation_exemptions
            WHERE guild_id = ?
            ORDER BY created_at ASC
        """;

        try {
            return database.query(conn -> {
                List<UserID> userIDs = new ArrayList<>();
                List<RoleID> roleIDs = new ArrayList<>();

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
                            }
                        }
                    }
                }

                return new ExcludedEntities(List.copyOf(userIDs), List.copyOf(roleIDs));
            });
        } catch (Exception e) {
            logger.error("Failed to fetch excluded users and roles", e);
            return new ExcludedEntities(List.of(), List.of());
        }
    }

    /**
     * Checks whether moderation should be skipped for a member based on exclusions.
     *
     * <p>User-level exclusions are evaluated first and take priority over role-level exclusions.
     *
     * @param guildID guild scope for exclusions
     * @param userID member user id
     * @param roleIDs member role ids
     * @return {@code true} if the user or any role is excluded; otherwise {@code false}
     */
    public boolean isExcluded(@NotNull GuildID guildID, @NotNull UserID userID, @NotNull Collection<RoleID> roleIDs) {
        if (isExcluded(guildID, userID)) {
            return true;
        }

        for (RoleID roleID : roleIDs) {
            if (isExcluded(guildID, roleID)) {
                return true;
            }
        }

        return false;
    }

}
