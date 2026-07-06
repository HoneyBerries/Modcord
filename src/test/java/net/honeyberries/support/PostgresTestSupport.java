package net.honeyberries.support;

import net.honeyberries.database.Database;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.DockerImageName;

/**
 * Base class for tests that need a real Postgres database.
 * <p>
 * Starts a single Postgres container for the whole test JVM (Testcontainers'
 * singleton container pattern) and points {@link Database} at it via Liquibase
 * migrations, instead of the real Azure-hosted database referenced by
 * {@code config/app_config.yml}. The container is reaped by Testcontainers'
 * Ryuk sidecar when the JVM exits; there is no explicit shutdown.
 */
public abstract class PostgresTestSupport {

    protected static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer(DockerImageName.parse("postgres:18-alpine"));

    static {
        POSTGRES.start();
        Database.getInstance().initialize(POSTGRES.getJdbcUrl(), POSTGRES.getUsername(), POSTGRES.getPassword());
    }
}
