import aiosqlite

from modcord.util.logger import get_logger

logger = get_logger("database_schema")


class SchemaManager:
    """Simple schema initializer for SQLite, no migrations."""

    @staticmethod
    async def initialize_schema(db: aiosqlite.Connection) -> None:
        """Create all tables, indexes, and triggers if they don't exist."""
        try:
            # Tables
            await db.executescript("""
                CREATE TABLE IF NOT EXISTS guild_settings (
                    guild_id INTEGER PRIMARY KEY,
                    ai_enabled INTEGER NOT NULL DEFAULT 1,
                    rules TEXT NOT NULL DEFAULT '',
                    auto_warn_enabled INTEGER NOT NULL DEFAULT 1,
                    auto_delete_enabled INTEGER NOT NULL DEFAULT 1,
                    auto_timeout_enabled INTEGER NOT NULL DEFAULT 1,
                    auto_kick_enabled INTEGER NOT NULL DEFAULT 1,
                    auto_ban_enabled INTEGER NOT NULL DEFAULT 1,
                    mod_log_channel_id INTEGER DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );


                CREATE TABLE IF NOT EXISTS channel_guidelines (
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    guidelines TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (guild_id, channel_id),
                    FOREIGN KEY (guild_id) REFERENCES guild_settings(guild_id) ON DELETE CASCADE
                );
            """)

            # Indexes
            await db.executescript("""
                CREATE INDEX IF NOT EXISTS idx_channel_guidelines_guild ON channel_guidelines(guild_id);
            """)

            # Triggers
            await db.executescript("""
                CREATE TRIGGER IF NOT EXISTS update_guild_settings_timestamp
                AFTER UPDATE ON guild_settings
                FOR EACH ROW
                BEGIN
                    UPDATE guild_settings SET updated_at = CURRENT_TIMESTAMP
                    WHERE guild_id = NEW.guild_id;
                END;

                CREATE TRIGGER IF NOT EXISTS update_channel_guidelines_timestamp
                AFTER UPDATE ON channel_guidelines
                FOR EACH ROW
                BEGIN
                    UPDATE channel_guidelines SET updated_at = CURRENT_TIMESTAMP
                    WHERE guild_id = NEW.guild_id AND channel_id = NEW.channel_id;
                END;
            """)

            await db.commit()
            logger.info("[SCHEMA] Database schema initialized successfully")

        except Exception as e:
            logger.exception("[SCHEMA] Failed to initialize schema: %s", e)
            raise
