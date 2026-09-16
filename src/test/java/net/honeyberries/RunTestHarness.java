package net.honeyberries;

import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.DockerImageName;

/**
 * Entry point for the {@code runTest} Gradle task.
 * <p>
 * Starts a throwaway Testcontainers-managed Postgres instance, points {@link Main} at it via
 * the {@code db.*} system property overrides in {@link net.honeyberries.database.Database}, and
 * then defers to the real, unmodified {@link Main#main(String[])} with the {@code --test} flag.
 * This keeps {@code runTest} a genuine "does the whole program boot" smoke test that exercises
 * the exact same startup path as {@code ./gradlew run}, without depending on network access to
 * any shared external database.
 */
public class RunTestHarness {

    static void main() {
        PostgreSQLContainer postgres = new PostgreSQLContainer(DockerImageName.parse("postgres:18-alpine"));
        postgres.start();
        Runtime.getRuntime().addShutdownHook(new Thread(postgres::stop));

        System.setProperty("db.url", postgres.getJdbcUrl());
        System.setProperty("db.username", postgres.getUsername());
        System.setProperty("db.password", postgres.getPassword());

        Main.main(new String[]{"--runtest"});
    }
}
