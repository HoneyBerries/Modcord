package net.honeyberries.database;

import net.honeyberries.config.AppConfig;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Tag;

/**
 * Base class for database integration tests.
 * Handles initialization and cleanup to ensure test isolation.
 */
@Tag("integration")
public abstract class DatabaseIntegrationTest {

    protected static final Database database = Database.getInstance();
    protected static final AppConfig appConfig = AppConfig.getInstance();

    @BeforeAll
    static void initializeDatabase() {
        database.initialize(appConfig);
    }

    @BeforeEach
    void cleanupTestData() {
        // Subclasses override to clean their specific test data
    }

    protected void deleteFromTable(String tableName, String whereClause, long... values) {
        StringBuilder sql = new StringBuilder("DELETE FROM ").append(tableName);
        if (whereClause != null && !whereClause.isEmpty()) {
            sql.append(" WHERE ").append(whereClause);
        }

        database.executeUpdate(conn -> {
            try (var stmt = conn.prepareStatement(sql.toString())) {
                for (int i = 0; i < values.length; i++) {
                    stmt.setLong(i + 1, values[i]);
                }
                return stmt.executeUpdate();
            }
        });
    }
}
