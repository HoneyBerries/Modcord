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
                    auto_review_enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS guild_moderator_roles (
                    guild_id INTEGER NOT NULL,
                    role_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (guild_id, role_id),
                    FOREIGN KEY (guild_id) REFERENCES guild_settings(guild_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS guild_review_channels (
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (guild_id, channel_id),
                    FOREIGN KEY (guild_id) REFERENCES guild_settings(guild_id) ON DELETE CASCADE
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

                CREATE TABLE IF NOT EXISTS moderation_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    timeout_duration INTEGER NOT NULL DEFAULT 0,
                    ban_duration INTEGER NOT NULL DEFAULT 0,
                    message_ids TEXT NOT NULL DEFAULT '',
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Indexes
            await db.executescript("""
                CREATE INDEX IF NOT EXISTS idx_moderator_roles_guild ON guild_moderator_roles(guild_id);
                CREATE INDEX IF NOT EXISTS idx_review_channels_guild ON guild_review_channels(guild_id);
                CREATE INDEX IF NOT EXISTS idx_channel_guidelines_guild ON channel_guidelines(guild_id);

                CREATE INDEX IF NOT EXISTS idx_moderation_actions_lookup 
                    ON moderation_actions(guild_id, user_id, timestamp);
                CREATE INDEX IF NOT EXISTS idx_moderation_actions_timestamp 
                    ON moderation_actions(timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_moderation_actions_user 
                    ON moderation_actions(user_id, guild_id);
                CREATE INDEX IF NOT EXISTS idx_moderation_actions_action 
                    ON moderation_actions(action, guild_id);
                CREATE INDEX IF NOT EXISTS idx_moderation_actions_bulk 
                    ON moderation_actions(guild_id, timestamp DESC, user_id);
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
