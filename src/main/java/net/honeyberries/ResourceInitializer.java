package net.honeyberries;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

public class ResourceInitializer {
    private static final Logger logger = LoggerFactory.getLogger(ResourceInitializer.class);

    public static void initialize() {
        try {
            Files.createDirectories(Paths.get("./config"));
            copyIfMissing("app_config.yml", "./config/app_config.yml");
            copyIfMissing("system_prompt.md", "./config/system_prompt.md");
            copyIfMissing(".env.example", "./.env.example");
        } catch (IOException e) {
            logger.error("Failed to initialize resources", e);
            throw new RuntimeException(e);
        }
    }

    private static void copyIfMissing(String resource, String target) throws IOException {
        Path targetPath = Paths.get(target);
        if (Files.exists(targetPath)) return;

        try (InputStream in = ResourceInitializer.class.getResourceAsStream("/" + resource)) {
            if (in == null) throw new IOException("Resource not found: " + resource);
            Files.copy(in, targetPath);
            logger.info("Created {}", target);
        }
    }
}
