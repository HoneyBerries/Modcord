package net.honeyberries.database;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import net.honeyberries.config.AppConfig;
import net.honeyberries.util.TokenManager;
import liquibase.Liquibase;
import liquibase.database.DatabaseFactory;
import liquibase.database.jvm.JdbcConnection;
import liquibase.resource.ClassLoaderResourceAccessor;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

/**
 * Central database coordinator for Modcord as a singleton.
 * Manages the lifecycle of the PostgreSQL connection pool, schema migrations, and provides convenient helpers for reading, writing, and transactional operations.
 * Designed to be friendly to use with automatic connection handling and support for lambdas that may throw {@link SQLException}.
 *
 * <p><b>Typical usage</b>
 * <pre>{@code
 * Database db = Database.getInstance();
 * db.initialize(config);
 *
 * String name = db.query(conn -> {
 *     try (PreparedStatement stmt = conn.prepareStatement(
 *             "SELECT name FROM users WHERE interactionID = ?")) {
 *         stmt.setLong(1, userId);
 *         try (ResultSet rs = stmt.executeQuery()) {
 *             return rs.next() ? rs.getString("name") : null;
 *         }
 *     }
 * });
 *
 * db.transaction(conn -> {
 *     try (PreparedStatement stmt = conn.prepareStatement(
 *             "INSERT INTO logs(message) VALUES (?)")) {
 *         stmt.setString(1, "hello");
 *         stmt.executeUpdate();
 *     }
 * });
 * }</pre>
 */
public class Database {
    private static final Logger logger = LoggerFactory.getLogger(Database.class);
    private static final Database INSTANCE = new Database();

    private volatile HikariDataSource dataSource;
    private volatile boolean initialized = false;


    /**
     * Returns the singleton instance of the database coordinator.
     * 
     * @return the singleton {@code Database} instance, never {@code null}
     */
    @NotNull
    public static Database getInstance() {
        return INSTANCE;
    }

    // ──────────────────────────────────────────────────────────────────
    // Functional interfaces
    // ──────────────────────────────────────────────────────────────────

    @FunctionalInterface
    public interface SqlQuery<T> {
        T execute(Connection conn) throws SQLException;
    }

    @FunctionalInterface
    public interface SqlWork {
        void execute(Connection conn) throws SQLException;
    }

    @FunctionalInterface
    public interface StatementBinder {
        void bind(PreparedStatement stmt);
    }

    @FunctionalInterface
    public interface RowMapper<T> {
        T map(ResultSet rs);
    }

    // ──────────────────────────────────────────────────────────────────
    // Lifecycle
    // ──────────────────────────────────────────────────────────────────

    /**
     * Opens the connection pool and initializes the database schema via Liquibase migrations.
     * Must be called once before any database operations.
     *
     * @param config the application configuration containing database URL, username, and password environment variable reference, must not be {@code null}
     * @throws NullPointerException if {@code config} is {@code null}
     * @throws DatabaseException if initialization fails, including when POSTGRES_DB_PASSWORD environment variable is not set or if schema initialization fails
     */
    public synchronized void initialize(@NotNull AppConfig config) {
        if (initialized) {
            logger.debug("Already initialized, skipping");
            return;
        }

        String dbUrl = config.getDatabaseUrl();
        String dbUsername = config.getDatabaseUsername();
        String dbPassword = TokenManager.getDBPassword();

        if (dbPassword.isBlank()) {
            throw new DatabaseException("POSTGRES_DB_PASSWORD environment variable is not set");
        }

        logger.info("Initializing PostgreSQL connection pool at {}", dbUrl);

        HikariConfig hikariConfig = createHikariConfig(dbUrl, dbUsername, dbPassword);

        try {
            dataSource = new HikariDataSource(hikariConfig);
        } catch (Exception e) {
            throw new DatabaseException("Failed to open connection pool", e);
        }

        try (Connection conn = dataSource.getConnection()) {
            liquibase.database.Database database = DatabaseFactory.getInstance()
                    .findCorrectDatabaseImplementation(new JdbcConnection(conn));

            try (Liquibase liquibase = new Liquibase("db/changelog/db.changelog-master.xml",
                    new ClassLoaderResourceAccessor(), database)) {
                logger.info("Running database migrations via Liquibase");
                liquibase.update();
                logger.info("Database migrations completed successfully");
            }
        } catch (Exception e) {
            closePoolSilently();
            throw new DatabaseException("Schema initialization failed", e);
        }

        initialized = true;
        logger.info("Ready at {}", dbUrl);
    }

    /**
     * Creates and configures a {@link HikariConfig} object with the provided database connection parameters.
     * The configuration includes setting the JDBC URL, username, password, and a predefined pool name.
     *
     * @param dbUrl the JDBC URL of the database, must not be {@code null}
     * @param dbUsername the username for the database connection, must not be {@code null}
     * @param dbPassword the password for the database connection, must not be {@code null}
     * @return a configured {@code HikariConfig} instance, never {@code null}
     */
    @NotNull
    private static HikariConfig createHikariConfig(@NotNull String dbUrl, @NotNull String dbUsername, @NotNull String dbPassword) {
        HikariConfig hikariConfig = new HikariConfig();
        
        hikariConfig.setJdbcUrl(dbUrl);
        hikariConfig.setUsername(dbUsername);
        hikariConfig.setPassword(dbPassword);
        
        hikariConfig.setPoolName("Modcord-Postgres-Pool");
        
        return hikariConfig;
    }

    /**
     * Shuts down the connection pool and releases all resources.
     * Safe to call even if the database has not been initialized.
     */
    public synchronized void shutdown() {
        if (!initialized && dataSource == null) {
            return;
        }

        initialized = false;
        closePoolSilently();
        logger.info("Database shutdown completed successfully");
    }

    private void closePoolSilently() {
        if (dataSource != null) {
            try {
                dataSource.close();
            } finally {
                dataSource = null;
            }
        }
    }

    // ──────────────────────────────────────────────────────────────────
    // Friendly SQL helpers
    // ──────────────────────────────────────────────────────────────────

    /**
     * Runs a read-only query operation and returns its result.
     * The connection is automatically obtained from the pool and closed after the operation completes.
     *
     * @param <T> the result type of the query
     * @param work the query operation to execute, must not be {@code null}
     * @return the result of the query, which may be {@code null} if the operation returns {@code null}
     * @throws NullPointerException if {@code work} is {@code null}
     * @throws DatabaseException if a database error occurs
     */
    public <T> T query(@NotNull SqlQuery<T> work) {
        ensureInitialized();
        try (Connection conn = dataSource.getConnection()) {
            return work.execute(conn);
        } catch (SQLException e) {
            throw new DatabaseException("Query failed", e);
        }
    }

    /**
     * Runs a write operation inside an automatic transaction.
     * If the operation completes without throwing an exception, the transaction is committed.
     * If a {@link SQLException} or {@link RuntimeException} is thrown, the transaction is rolled back.
     * Auto-commit is restored after the transaction completes or fails.
     *
     * @param work the write operation to execute within the transaction, must not be {@code null}
     * @throws NullPointerException if {@code work} is {@code null}
     * @throws DatabaseException if a database error occurs or the transaction fails
     */
    public void transaction(@NotNull SqlWork work) {
        ensureInitialized();
        try (Connection conn = dataSource.getConnection()) {
            conn.setAutoCommit(false);
            try {
                work.execute(conn);
                conn.commit();
            } catch (SQLException e) {
                safeRollback(conn);
                throw new DatabaseException("Transaction failed", e);
            } catch (RuntimeException e) {
                safeRollback(conn);
                throw e;
            } finally {
                safeResetAutoCommit(conn);
            }
        } catch (SQLException e) {
            throw new DatabaseException("Transaction failed", e);
        }
    }

    /**
     * Executes an update/insert/delete statement and returns the number of affected rows.
     * 
     * @param work the query operation that executes the update and returns an integer count, must not be {@code null}
     * @return the number of rows affected by the update; 0 if the operation returns {@code null}
     * @throws NullPointerException if {@code work} is {@code null}
     * @throws DatabaseException if a database error occurs
     */
    public int executeUpdate(@NotNull SqlQuery<Integer> work) {
        Integer result = query(work);
        return result == null ? 0 : result;
    }

    /**
     * Runs a query that may return a single value.
     * 
     * @param <T> the result type of the query
     * @param work the query operation to execute, must not be {@code null}
     * @return the result of the query, which may be {@code null}
     * @throws NullPointerException if {@code work} is {@code null}
     * @throws DatabaseException if a database error occurs
     */
    @Nullable
    public <T> T queryOne(@NotNull SqlQuery<T> work) {
        return query(work);
    }

    /**
     * Runs a query and returns null when no row is found.
     * 
     * @param <T> the result type of the query
     * @param work the query operation to execute, must not be {@code null}
     * @return the result of the query, which may be {@code null} if no row is found or the query returns {@code null}
     * @throws NullPointerException if {@code work} is {@code null}
     * @throws DatabaseException if a database error occurs
     */
    @Nullable
    public <T> T queryNullable(@NotNull SqlQuery<T> work) {
        return query(work);
    }

    /**
     * Checks whether the database pool is initialized and healthy.
     * Performs a quick connection validity check (1-second timeout).
     * 
     * @return {@code true} if the pool is initialized and a valid connection can be obtained, {@code false} otherwise
     */
    public boolean isHealthy() {
        if (!initialized || dataSource == null) return false;
        try (Connection conn = dataSource.getConnection()) {
            return conn.isValid(1);
        } catch (SQLException e) {
            logger.warn("Health check failed", e);
            return false;
        }
    }




    private void safeRollback(Connection conn) {
        try {
            conn.rollback();
        } catch (SQLException rollbackError) {
            logger.warn("Rollback failed", rollbackError);
        }
    }

    private void safeResetAutoCommit(Connection conn) {
        try {
            conn.setAutoCommit(true);
        } catch (SQLException resetError) {
            logger.warn("Failed to restore auto-commit", resetError);
        }
    }

    private void ensureInitialized() {
        if (!initialized || dataSource == null) {
            throw new IllegalStateException("Database has not been initialized");
        }
    }

    // ──────────────────────────────────────────────────────────────────
    // Exception
    // ──────────────────────────────────────────────────────────────────

    /**
     * Exception thrown when a database operation fails.
     * Wraps checked exceptions ({@link SQLException}) and database lifecycle errors into an unchecked exception.
     */
    public static class DatabaseException extends RuntimeException {
        /**
         * Constructs a new exception with the specified detail message.
         *
         * @param message the error message, must not be {@code null}
         */
        public DatabaseException(@NotNull String message) {
            super(message);
        }

        /**
         * Constructs a new exception with the specified detail message and cause.
         *
         * @param message the error message, must not be {@code null}
         * @param cause the underlying exception that caused this error, may be {@code null}
         */
        public DatabaseException(@NotNull String message, @Nullable Throwable cause) {
            super(message, cause);
        }
    }
}