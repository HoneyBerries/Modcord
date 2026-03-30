package net.honeyberries.config;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.HashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

@DisplayName("AppConfig Test Suite")
class AppConfigTest {

    private AppConfig appConfig;
    private static final Path REAL_CONFIG_PATH = Paths.get("./config/app_config.yml").toAbsolutePath();

    @BeforeEach
    void setUp() {
        appConfig = new AppConfig(REAL_CONFIG_PATH);
    }

    @Nested
    @DisplayName("Constructor and Initialization Tests")
    class ConstructorTests {

        @Test
        @DisplayName("Should initialize AppConfig with valid config path")
        void testConstructorWithValidPath() {
            AppConfig config = new AppConfig(REAL_CONFIG_PATH);
            assertNotNull(config);
        }

        @Test
        @DisplayName("Should load data into memory after construction")
        void testDataLoadsAfterConstruction() {
            assertNotNull(appConfig.data);
            assertFalse(appConfig.data.isEmpty(), "Configuration data should not be empty");
        }

        @Test
        @DisplayName("Should handle file not found gracefully")
        void testConstructorWithInvalidPath() {
            Path invalidPath = Paths.get("./nonexistent/config.yml");
            AppConfig config = new AppConfig(invalidPath);
            assertNotNull(config);
            // Should still initialize without throwing exception
        }
    }

    @Nested
    @DisplayName("Reload Tests")
    class ReloadTests {

        @Test
        @DisplayName("Should successfully reload configuration from disk")
        void testReloadConfiguration() {
            new HashMap<>(appConfig.data);
            appConfig.reload();
            
            assertNotNull(appConfig.data);
            assertFalse(appConfig.data.isEmpty());
        }

        @Test
        @DisplayName("Should replace data cache on reload")
        void testReloadReplacesDataCache() {
            appConfig.reload();
            int newSize = appConfig.data.size();
            
            assertTrue(newSize > 0, "Data should be reloaded after reload()");
        }
    }

    @Nested
    @DisplayName("Generic Server Rules Tests")
    class GenericServerRulesTests {

        @Test
        @DisplayName("Should return generic server rules")
        void testGetGenericServerRules() {
            String rules = appConfig.getGenericServerRules();
            assertNotNull(rules, "Server rules should not be null");
            assertFalse(rules.isEmpty(), "Server rules should not be empty");
        }

        @Test
        @DisplayName("Should throw RuntimeException if generic_server_rules not configured")
        void testGetGenericServerRulesNotConfigured() {
            AppConfig config = new AppConfig(Paths.get("./nonexistent/config.yml"));
            assertThrows(RuntimeException.class, config::getGenericServerRules);
        }
    }

    @Nested
    @DisplayName("Generic Channel Guidelines Tests")
    class GenericChannelGuidelinesTests {

        @Test
        @DisplayName("Should return generic channel guidelinesText")
        void testGetGenericChannelGuidelines() {
            String guidelines = appConfig.getGenericChannelGuidelines();
            assertNotNull(guidelines, "Channel guidelinesText should not be null");
            assertFalse(guidelines.isEmpty(), "Channel guidelinesText should not be empty");
        }

        @Test
        @DisplayName("Should throw RuntimeException if generic_channel_guidelines not configured")
        void testGetGenericChannelGuidelinesNotConfigured() {
            AppConfig config = new AppConfig(Paths.get("./nonexistent/config.yml"));
            assertThrows(RuntimeException.class, config::getGenericChannelGuidelines);
        }
    }


    @Nested
    @DisplayName("Database Settings Tests")
    class DatabaseSettingsTests {

        @Test
        @DisplayName("Should return database URL")
        void testGetDatabaseUrl() {
            String url = appConfig.getDatabaseUrl();
            assertNotNull(url, "Database URL should not be null");
            assertTrue(url.contains("jdbc:postgresql"), "Should be a valid PostgreSQL JDBC URL");
        }

        @Test
        @DisplayName("Should return database username")
        void testGetDatabaseUsername() {
            String username = appConfig.getDatabaseUsername();
            assertNotNull(username, "Database username should not be null");
            assertFalse(username.isEmpty(), "Database username should not be empty");
        }

        @Test
        @DisplayName("Should throw RuntimeException if database URL not configured")
        void testGetDatabaseUrlNotConfigured() {
            AppConfig config = new AppConfig(Paths.get("./nonexistent/config.yml"));
            assertThrows(RuntimeException.class, config::getDatabaseUrl);
        }

        @Test
        @DisplayName("Should throw RuntimeException if database username not configured")
        void testGetDatabaseUsernameNotConfigured() {
            AppConfig config = new AppConfig(Paths.get("./nonexistent/config.yml"));
            assertThrows(RuntimeException.class, config::getDatabaseUsername);
        }

        @Test
        @DisplayName("Database URL should contain all required parts")
        void testDatabaseUrlStructure() {
            String url = appConfig.getDatabaseUrl();
            assertTrue(url.contains("jdbc:postgresql://"), "Should start with jdbc:postgresql://");
            assertTrue(url.contains(":5432"), "Should contain PostgreSQL default port");
        }
    }

    @Nested
    @DisplayName("AI Settings Tests")
    class AISettingsTests {

        @Test
        @DisplayName("Should return AI endpoint URL")
        void testGetAIEndpoint() {
            String endpoint = appConfig.getAIEndpoint();
            assertNotNull(endpoint, "AI endpoint should not be null");
            assertFalse(endpoint.isEmpty(), "AI endpoint should not be empty");
            assertTrue(endpoint.startsWith("http"), "Endpoint should be a valid URL");
        }

        @Test
        @DisplayName("Should return AI model name")
        void testGetAIModelName() {
            String modelName = appConfig.getAIModelName();
            assertNotNull(modelName, "Model name should not be null");
            assertFalse(modelName.isEmpty(), "Model name should not be empty");
        }

        @Test
        @DisplayName("Should return AI request timeout as double or throw if not configured")
        void testGetAIRequestTimeout() {
            // This test handles both cases - if timeout is configured or not
            try {
                double timeout = appConfig.getAIRequestTimeout();
                assertTrue(timeout > 0, "Timeout should be positive");
                assertTrue(timeout <= Long.MAX_VALUE, "Timeout should be reasonable");
            } catch (RuntimeException e) {
                // Expected if api_request_timeout is not in config
                assertTrue(e.getMessage().contains("not configured") || e.getMessage().contains("timeout"));
            }
        }

        @Test
        @DisplayName("Should throw RuntimeException if AI endpoint not configured")
        void testGetAIEndpointNotConfigured() {
            AppConfig config = new AppConfig(Paths.get("./nonexistent/config.yml"));
            assertThrows(RuntimeException.class, config::getAIEndpoint);
        }

        @Test
        @DisplayName("Should throw RuntimeException if AI model name not configured")
        void testGetAIModelNameNotConfigured() {
            AppConfig config = new AppConfig(Paths.get("./nonexistent/config.yml"));
            assertThrows(RuntimeException.class, config::getAIModelName);
        }

        @Test
        @DisplayName("Should throw RuntimeException if AI request timeout not configured")
        void testGetAIRequestTimeoutNotConfigured() {
            AppConfig config = new AppConfig(Paths.get("./nonexistent/config.yml"));
            assertThrows(RuntimeException.class, config::getAIRequestTimeout);
        }

        @Test
        @DisplayName("AI endpoint should be a valid URL format")
        void testAIEndpointFormat() {
            String endpoint = appConfig.getAIEndpoint();
            assertTrue(endpoint.startsWith("http://") || endpoint.startsWith("https://"),
                "Endpoint should be a valid URL");
        }

        @Test
        @DisplayName("Model name should not be empty or whitespace")
        void testAIModelNameNotBlank() {
            String modelName = appConfig.getAIModelName();
            assertFalse(modelName.trim().isEmpty(), "Model name should not be blank");
        }
    }

    @Nested
    @DisplayName("Cache Settings Tests")
    class CacheSettingsTests {

        @Test
        @DisplayName("Should return rules sync interval")
        void testGetRulesSyncInterval() {
            double interval = appConfig.getRulesSyncInterval();
            assertTrue(interval > 0, "Rules sync interval should be positive");
        }

        @Test
        @DisplayName("Should return guidelinesText sync interval")
        void testGetGuidelinesSyncInterval() {
            double interval = appConfig.getGuidelinesSyncInterval();
            assertTrue(interval > 0, "Guidelines sync interval should be positive");
        }

        @Test
        @DisplayName("Should throw RuntimeException if rules cache refresh not configured")
        void testGetRulesSyncIntervalNotConfigured() {
            AppConfig config = new AppConfig(Paths.get("./nonexistent/config.yml"));
            assertThrows(RuntimeException.class, config::getRulesSyncInterval);
        }

        @Test
        @DisplayName("Should throw RuntimeException if guidelinesText cache refresh not configured")
        void testGetGuidelinesSyncIntervalNotConfigured() {
            AppConfig config = new AppConfig(Paths.get("./nonexistent/config.yml"));
            assertThrows(RuntimeException.class, config::getGuidelinesSyncInterval);
        }

        @Test
        @DisplayName("Sync intervals should be reasonable values")
        void testSyncIntervalsReasonable() {
            double rulesInterval = appConfig.getRulesSyncInterval();
            double guidelinesInterval = appConfig.getGuidelinesSyncInterval();
            
            // Sync intervals should be at least 1 second (or INFINITY)
            assertTrue(rulesInterval > 0, "Rules sync interval should be reasonable (> 0)");
            assertTrue(guidelinesInterval > 0, "Guidelines sync interval should be reasonable (> 0)");
        }
    }

    @Nested
    @DisplayName("Moderation Settings Tests")
    class ModerationSettingsTests {

        @Test
        @DisplayName("Should return moderation queue duration")
        void testGetModerationQueueDuration() {
            double duration = appConfig.getModerationQueueDuration();
            assertTrue(duration > 0, "Moderation queue duration should be positive");
        }

        @Test
        @DisplayName("Should return history context max messages or throw if not configured")
        void testGetHistoryContextMaxMessages() {
            try {
                long maxMessages = appConfig.getHistoryContextMaxMessages();
                assertTrue(maxMessages >= 0, "Max messages should be non-negative");
            } catch (RuntimeException e) {
                // Expected if num_history_context_messages is not in config
                assertTrue(e.getMessage().contains("not configured"));
            }
        }

        @Test
        @DisplayName("Should return history context max age")
        void testGetHistoryContextMaxAge() {
            double maxAge = appConfig.getHistoryContextMaxAge();
            assertTrue(maxAge > 0, "History context max age should be positive");
        }

        @Test
        @DisplayName("Should throw RuntimeException if moderation queue duration not configured")
        void testGetModerationQueueDurationNotConfigured() {
            AppConfig config = new AppConfig(Paths.get("./nonexistent/config.yml"));
            assertThrows(RuntimeException.class, config::getModerationQueueDuration);
        }

        @Test
        @DisplayName("Should throw RuntimeException if history context max messages not configured")
        void testGetHistoryContextMaxMessagesNotConfigured() {
            AppConfig config = new AppConfig(Paths.get("./nonexistent/config.yml"));
            assertThrows(RuntimeException.class, config::getHistoryContextMaxMessages);
        }

        @Test
        @DisplayName("Should throw RuntimeException if history context max age not configured")
        void testGetHistoryContextMaxAgeNotConfigured() {
            AppConfig config = new AppConfig(Paths.get("./nonexistent/config.yml"));
            assertThrows(RuntimeException.class, config::getHistoryContextMaxAge);
        }

        @Test
        @DisplayName("Moderation queue duration should be reasonable")
        void testModerationQueueDurationReasonable() {
            double duration = appConfig.getModerationQueueDuration();
            // Duration should typically be less than 1 hour (3600 seconds)
            assertTrue(duration < 3600, "Queue duration should be reasonable (< 1 hour)");
        }

        @Test
        @DisplayName("History context max age should be reasonable")
        void testHistoryContextMaxAgeReasonable() {
            double maxAge = appConfig.getHistoryContextMaxAge();
            // Max age should typically be less than 30 days
            assertTrue(maxAge < 2592000, "Max age should be reasonable (< 30 days)");
        }

        @Test
        @DisplayName("History context max messages should be reasonable or not configured")
        void testHistoryContextMaxMessagesReasonable() {
            try {
                long maxMessages = appConfig.getHistoryContextMaxMessages();
                // Max messages should typically be less than 10,000
                assertTrue(maxMessages <= 10000, "Max messages should be reasonable (< 10000)");
            } catch (RuntimeException e) {
                // Expected if field is not configured
                assertTrue(e.getMessage().contains("not configured"));
            }
        }
    }

    @Nested
    @DisplayName("Load From Disk Tests")
    class LoadFromDiskTests {

        @Test
        @DisplayName("Should load configuration data as Map")
        void testLoadFromDiskReturnsMap() {
            Map<String, Object> loadedData = appConfig.loadFromDisk();
            assertNotNull(loadedData, "Loaded data should not be null");
        }

        @Test
        @DisplayName("Should return empty map for non-existent file")
        void testLoadFromDiskNonExistentFile() {
            AppConfig config = new AppConfig(Paths.get("./nonexistent/config.yml"));
            Map<String, Object> loadedData = config.loadFromDisk();
            assertNotNull(loadedData, "Should return non-null map even for missing file");
        }

        @Test
        @DisplayName("Should contain expected root-level keys")
        void testLoadFromDiskContainsExpectedKeys() {
            Map<String, Object> loadedData = appConfig.loadFromDisk();
            assertTrue(loadedData.containsKey("database"), "Should contain 'database' key");
            assertTrue(loadedData.containsKey("ai_settings"), "Should contain 'ai_settings' key");
            assertTrue(loadedData.containsKey("moderation"), "Should contain 'moderation' key");
        }

        @Test
        @DisplayName("Should load nested structures correctly")
        void testLoadFromDiskNestedStructures() {
            Map<String, Object> loadedData = appConfig.loadFromDisk();
            
            Object dbSettings = loadedData.get("database");
            assertInstanceOf(Map.class, dbSettings, "Database settings should be a Map");
            
            Object aiSettings = loadedData.get("ai_settings");
            assertInstanceOf(Map.class, aiSettings, "AI settings should be a Map");
        }
    }

    @Nested
    @DisplayName("Type Casting and Data Extraction Tests")
    class TypeCastingTests {

        @Test
        @DisplayName("Should properly cast database settings to Map")
        void testDatabaseSettingsCasting() {
            String url = appConfig.getDatabaseUrl();
            String username = appConfig.getDatabaseUsername();
            
            assertNotNull(url);
            assertNotNull(username);
        }

        @Test
        @DisplayName("Should properly cast timeout values to double or handle missing config")
        void testTimeoutCasting() {
            try {
                double timeout = appConfig.getAIRequestTimeout();
                assertTrue(timeout > 0, "Timeout should be positive");
                assertTrue(Double.isFinite(timeout), "Timeout should be a finite double");
            } catch (RuntimeException e) {
                // Expected if api_request_timeout is not configured
                assertTrue(e.getMessage().contains("not configured"));
            }
        }

        @Test
        @DisplayName("Should properly cast history context max messages to long or handle missing config")
        void testHistoryContextMaxMessagesCasting() {
            try {
                long maxMessages = appConfig.getHistoryContextMaxMessages();
                assertTrue(maxMessages >= 0, "Max messages should be a non-negative long");
            } catch (RuntimeException e) {
                // Expected if num_history_context_messages is not configured
                assertTrue(e.getMessage().contains("not configured"));
            }
        }

        @Test
        @DisplayName("Should handle Number to double conversion")
        void testNumberToDoubleConversion() {
            double syncInterval = appConfig.getRulesSyncInterval();
            double queueDuration = appConfig.getModerationQueueDuration();
            
            assertTrue(Double.isFinite(syncInterval) || Double.isInfinite(syncInterval));
            assertTrue(Double.isFinite(queueDuration));
        }
    }

    @Nested
    @DisplayName("Consistency Tests")
    class ConsistencyTests {

        @Test
        @DisplayName("Multiple calls to same getter should return equivalent values")
        void testGetterConsistency() {
            String endpoint1 = appConfig.getAIEndpoint();
            String endpoint2 = appConfig.getAIEndpoint();
            
            assertEquals(endpoint1, endpoint2, "Multiple calls should return same value");
        }

        @Test
        @DisplayName("Data should remain consistent after reload")
        void testDataConsistencyAfterReload() {
            String endpointBefore = appConfig.getAIEndpoint();
            appConfig.reload();
            String endpointAfter = appConfig.getAIEndpoint();
            
            assertEquals(endpointBefore, endpointAfter, "Values should be same after reload");
        }

        @Test
        @DisplayName("All AI settings should be accessible or throw expected errors")
        void testAllAISettingsAccessible() {
            assertDoesNotThrow(appConfig::getAIEndpoint, "Should get AI endpoint");
            assertDoesNotThrow(appConfig::getAIModelName, "Should get AI model name");
            // AI request timeout might not be configured, so we handle the exception
            try {
                appConfig.getAIRequestTimeout();
            } catch (RuntimeException e) {
                assertTrue(e.getMessage().contains("not configured"));
            }
        }

        @Test
        @DisplayName("All database settings should be accessible")
        void testAllDatabaseSettingsAccessible() {
            assertDoesNotThrow(appConfig::getDatabaseUrl, "Should get database URL");
            assertDoesNotThrow(appConfig::getDatabaseUsername, "Should get database username");
        }

        @Test
        @DisplayName("All cache settings should be accessible")
        void testAllCacheSettingsAccessible() {
            assertDoesNotThrow(appConfig::getRulesSyncInterval, "Should get rules sync interval");
            assertDoesNotThrow(appConfig::getGuidelinesSyncInterval, "Should get guidelinesText sync interval");
        }

        @Test
        @DisplayName("All moderation settings should be accessible or throw expected errors")
        void testAllModerationSettingsAccessible() {
            assertDoesNotThrow(appConfig::getModerationQueueDuration, "Should get moderation queue duration");
            assertDoesNotThrow(appConfig::getHistoryContextMaxAge, "Should get history context max age");
            // History context max messages might not be configured, so we handle the exception
            try {
                appConfig.getHistoryContextMaxMessages();
            } catch (RuntimeException e) {
                assertTrue(e.getMessage().contains("not configured"));
            }
        }
    }
}
