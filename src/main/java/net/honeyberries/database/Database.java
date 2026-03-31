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
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

/**
 * Central database coordinator for Modcord.
 *
 * <p>This class is designed to be friendly to use:
 * <ul>
 *   <li>simple methods for reads, writes, and transactions</li>
 *   <li>lambdas may throw {@link SQLException}</li>
 *   <li>automatic connection handling</li>
 *   <li>convenience helpers for common query patterns</li>
 * </ul>
 *
 * <p><b>Typical usage</b>
 * <pre>{@code
 * Database db = Database.getInstance();
 * db.initialize(config);
 *
 * String name = db.query(conn -> {
 *     try (PreparedStatement stmt = conn.prepareStatement(
 *             "SELECT name FROM users WHERE id = ?")) {
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

    private HikariDataSource dataSource;
    private boolean initialized = false;


    /** Returns the singleton instance. */
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
     * Opens the connection pool and initializes the schema.
     *
     * @param config application config containing database URL and username
     * @throws DatabaseException if initialization fails
     */
    public synchronized void initialize(AppConfig config) {
        if (initialized) {
            logger.debug("Already initialized, skipping");
            return;
        }

        String dbUrl = config.getDatabaseUrl();
        String dbUsername = config.getDatabaseUsername();
        String dbPassword = TokenManager.getDBPassword();

        if (dbPassword.isBlank()) {
            throw new DatabaseException("MODCORD_DB_PASSWORD environment variable is not set");
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

    @NotNull
    private static HikariConfig createHikariConfig(String dbUrl, String dbUsername, String dbPassword) {
        HikariConfig hikariConfig = new HikariConfig();
        
        hikariConfig.setJdbcUrl(dbUrl);
        hikariConfig.setUsername(dbUsername);
        hikariConfig.setPassword(dbPassword);
        
        hikariConfig.setPoolName("Modcord-Postgres-Pool");
        
        return hikariConfig;
    }

    /** Shuts down the pool and releases all resources. */
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
     * Runs a read operation and returns its result.
     */
    public <T> T query(SqlQuery<T> work) {
        ensureInitialized();
        try (Connection conn = dataSource.getConnection()) {
            return work.execute(conn);
        } catch (SQLException e) {
            throw new DatabaseException("Query failed", e);
        }
    }

    /**
     * Runs a write operation inside a transaction.
     */
    public void transaction(SqlWork work) {
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
     * Executes an update/insert/delete statement and returns affected rows.
     */
    public int executeUpdate(SqlQuery<Integer> work) {
        Integer result = query(work);
        return result == null ? 0 : result;
    }

    /**
     * Runs a query that may return a single value.
     */
    public <T> T queryOne(SqlQuery<T> work) {
        return query(work);
    }

    /**
     * Runs a query and returns null when no row is found.
     */
    public <T> T queryNullable(SqlQuery<T> work) {
        return query(work);
    }

    /**
     * Returns true if the pool is initialized and healthy.
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

    public static class DatabaseException extends RuntimeException {
        public DatabaseException(String message) {
            super(message);
        }

        public DatabaseException(String message, Throwable cause) {
            super(message, cause);
        }
    }
}