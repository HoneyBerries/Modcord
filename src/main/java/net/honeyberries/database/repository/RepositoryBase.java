package net.honeyberries.database.repository;

import net.honeyberries.database.Database;
import net.honeyberries.database.Database.RowMapper;
import net.honeyberries.database.Database.SqlQuery;
import net.honeyberries.database.Database.SqlWork;
import net.honeyberries.database.Database.StatementBinder;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Types;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/**
 * Base class for the {@code database.repository} singletons.
 * <p>
 * Every repository built on top of {@link Database} repeats the same handful of shapes:
 * a logger, a reference to the {@link Database} singleton, a {@code try { ... } catch (Exception e)
 * { log; return defaultValue; }} wrapper around every call, and a {@code while (rs.next())} loop for
 * list-returning queries. This class centralizes that boilerplate so repositories can focus on their
 * SQL and row-mapping logic.
 *
 * <p>Subclasses remain responsible for their own singleton scaffolding ({@code static INSTANCE} /
 * {@code getInstance()}), since static members are not inherited polymorphically in Java, but should
 * otherwise prefer the {@code safeXxx} / {@code fetchXxx} helpers below over hand-rolled try/catch and
 * result-set loops.
 */
public abstract class RepositoryBase {

    /** Logger scoped to the concrete repository subclass. */
    protected final Logger logger = LoggerFactory.getLogger(getClass());
    /** Shared database connection pool. */
    protected final Database database = Database.getInstance();

    protected RepositoryBase() {}

    // ──────────────────────────────────────────────────────────────────
    // Error-wrapped call helpers (item 2: duplicated try/catch/log shape)
    // ──────────────────────────────────────────────────────────────────

    /**
     * Runs a read query via {@link Database#query}, logging {@code errorMessage} (with {@code args})
     * and returning {@code defaultOnError} if the query throws.
     *
     * @param work           the query to run
     * @param defaultOnError the value to return if the query fails
     * @param errorMessage   an SLF4J-style message (may contain {@code {}} placeholders for {@code args})
     * @param args           values to substitute into {@code errorMessage}; the triggering exception is
     *                       appended automatically and does not need to be included
     */
    @Nullable
    protected <T> T safeQuery(@NotNull SqlQuery<T> work, @Nullable T defaultOnError, @NotNull String errorMessage, Object... args) {
        try {
            return database.query(work);
        } catch (Exception e) {
            logError(errorMessage, args, e);
            return defaultOnError;
        }
    }

    /**
     * Convenience for read queries that produce a list: same as {@link #safeQuery} with
     * {@link List#of()} as the error default.
     */
    @NotNull
    protected <T> List<T> safeQueryForList(@NotNull SqlQuery<List<T>> work, @NotNull String errorMessage, Object... args) {
        List<T> result = safeQuery(work, List.of(), errorMessage, args);
        return result == null ? List.of() : result;
    }

    /**
     * Runs a write operation inside a transaction via {@link Database#transaction}, logging and
     * returning {@code false} if it throws, {@code true} on success.
     */
    protected boolean safeTransaction(@NotNull SqlWork work, @NotNull String errorMessage, Object... args) {
        try {
            database.transaction(work);
            return true;
        } catch (Exception e) {
            logError(errorMessage, args, e);
            return false;
        }
    }

    /**
     * Runs an update/insert/delete via {@link Database#executeUpdate}, logging and returning
     * {@code 0} if it throws.
     */
    protected int safeExecuteUpdate(@NotNull SqlQuery<Integer> work, @NotNull String errorMessage, Object... args) {
        try {
            return database.executeUpdate(work);
        } catch (Exception e) {
            logError(errorMessage, args, e);
            return 0;
        }
    }

    private void logError(@NotNull String errorMessage, @NotNull Object[] args, @NotNull Exception e) {
        Object[] withException = Arrays.copyOf(args, args.length + 1);
        withException[args.length] = e;
        logger.error(errorMessage, withException);
    }

    // ──────────────────────────────────────────────────────────────────
    // Query building blocks (item 3/4: duplicated list loops and row mapping)
    // ──────────────────────────────────────────────────────────────────

    /**
     * Prepares {@code sql} on {@code conn}, binds it via {@code binder}, and maps every result row
     * with {@code mapper} into a list. Meant to be called from inside a {@link SqlQuery} passed to
     * {@link #safeQuery} / {@link #safeQueryForList}.
     */
    @NotNull
    protected static <T> List<T> fetchList(@NotNull Connection conn, @NotNull String sql, @NotNull StatementBinder binder, @NotNull RowMapper<T> mapper) throws SQLException {
        List<T> results = new ArrayList<>();
        try (PreparedStatement ps = conn.prepareStatement(sql)) {
            binder.bind(ps);
            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    results.add(mapper.map(rs));
                }
            }
        }
        return results;
    }

    /**
     * Prepares {@code sql} on {@code conn}, binds it via {@code binder}, and maps the first result
     * row with {@code mapper}, or returns {@code null} if there is no matching row.
     */
    @Nullable
    protected static <T> T fetchOne(@NotNull Connection conn, @NotNull String sql, @NotNull StatementBinder binder, @NotNull RowMapper<T> mapper) throws SQLException {
        try (PreparedStatement ps = conn.prepareStatement(sql)) {
            binder.bind(ps);
            try (ResultSet rs = ps.executeQuery()) {
                return rs.next() ? mapper.map(rs) : null;
            }
        }
    }

    /**
     * All-in-one helper for the common case of "run this SELECT, map every row": wraps
     * {@link #fetchList} in {@link #safeQuery}, logging and returning an empty list on error.
     */
    @NotNull
    protected <T> List<T> safeQueryList(@NotNull String sql, @NotNull StatementBinder binder, @NotNull RowMapper<T> mapper, @NotNull String errorMessage, Object... args) {
        return safeQueryForList(conn -> fetchList(conn, sql, binder, mapper), errorMessage, args);
    }

    /**
     * All-in-one helper for the common case of "run this SELECT, map the first row (or none)":
     * wraps {@link #fetchOne} in {@link #safeQuery}, logging and returning {@code null} on error.
     */
    @Nullable
    protected <T> T safeQueryOne(@NotNull String sql, @NotNull StatementBinder binder, @NotNull RowMapper<T> mapper, @NotNull String errorMessage, Object... args) {
        return safeQuery(conn -> fetchOne(conn, sql, binder, mapper), null, errorMessage, args);
    }

    // ──────────────────────────────────────────────────────────────────
    // Nullable typed-ID binding (item 5)
    // ──────────────────────────────────────────────────────────────────

    /**
     * Binds a nullable snowflake value at {@code index}: {@code setLong} if present, otherwise
     * {@code setNull(index, Types.BIGINT)}. Typed-ID wrappers (e.g. {@code ChannelID}, {@code RoleID})
     * are unwrapped by the caller: {@code bindNullableLong(ps, 3, channelId == null ? null : channelId.value())}.
     */
    protected static void bindNullableLong(@NotNull PreparedStatement ps, int index, @Nullable Long value) throws SQLException {
        if (value != null) {
            ps.setLong(index, value);
        } else {
            ps.setNull(index, Types.BIGINT);
        }
    }
}
