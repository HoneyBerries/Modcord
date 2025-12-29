"""
Database schema initialization and migration management.

Handles creation of tables, indexes, triggers, and schema version tracking.
"""

import aiosqlite
from modcord.util.logger import get_logger

logger = get_logger("database_schema")


class SchemaManager:
    """Manages database schema creation and migrations.
    
    Provides methods to initialize and update the database schema,
    including tables, indexes, and triggers."""
    
    @staticmethod
    async def initialize_schema(db: aiosqlite.Connection) -> None:
        """
        Create or update all database tables, indexes, and triggers.
        
        Args:
            db: Open database connection
        """
        await SchemaManager._create_tables(db)
        await SchemaManager._create_indexes(db)
        await SchemaManager._create_triggers(db)
        await SchemaManager._update_schema_version(db)
        await db.commit()
        logger.info("[SCHEMA] Database schema initialized")
    
    @staticmethod
    async def _create_tables(db: aiosqlite.Connection) -> None:
        """Create all required database tables."""
        # Guild settings table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id INTEGER PRIMARY KEY,
                ai_enabled INTEGER NOT NULL DEFAULT 1,
                rules TEXT NOT NULL DEFAULT '',
                auto_warn_enabled INTEGER NOT NULL DEFAULT 1,
                auto_delete_enabled INTEGER NOT NULL DEFAULT 1,
                auto_timeout_enabled INTEGER NOT NULL DEFAULT 1,
                auto_kick_enabled INTEGER NOT NULL DEFAULT 1,
                auto_ban_enabled INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                auto_review_enabled INTEGER NOT NULL DEFAULT 1
            )
        """)
        
        # Migration: add auto_review_enabled if missing
        try:
            await db.execute(
                "ALTER TABLE guild_settings ADD COLUMN auto_review_enabled INTEGER NOT NULL DEFAULT 1"
            )
            logger.info("[SCHEMA] Added auto_review_enabled column to guild_settings")
        except Exception:
            pass  # Column already exists
        
        # Moderator roles table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS guild_moderator_roles (
                guild_id INTEGER NOT NULL,
                role_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (guild_id, role_id),
                FOREIGN KEY (guild_id) REFERENCES guild_settings(guild_id) ON DELETE CASCADE
            )
        """)
        
        # Review channels table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS guild_review_channels (
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (guild_id, channel_id),
                FOREIGN KEY (guild_id) REFERENCES guild_settings(guild_id) ON DELETE CASCADE
            )
        """)
        
        # Channel guidelines table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS channel_guidelines (
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                guidelines TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (guild_id, channel_id),
                FOREIGN KEY (guild_id) REFERENCES guild_settings(guild_id) ON DELETE CASCADE
            )
        """)
        
        # Moderation actions table (recreate for schema updates)
        await db.execute("DROP TABLE IF EXISTS moderation_actions")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS moderation_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                user_id TEXT NOT NULL,
                action TEXT NOT NULL,
                reason TEXT NOT NULL,
                timeout_duration INTEGER NOT NULL DEFAULT 0,
                ban_duration INTEGER NOT NULL DEFAULT 0,
                message_ids TEXT NOT NULL DEFAULT '',
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Schema version table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    
    @staticmethod
    async def _create_indexes(db: aiosqlite.Connection) -> None:
        """Create strategic indexes for query optimization."""
        # Existing indexes
        await db.execute("CREATE INDEX IF NOT EXISTS idx_moderator_roles_guild ON guild_moderator_roles(guild_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_review_channels_guild ON guild_review_channels(guild_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_moderation_actions_lookup ON moderation_actions(guild_id, user_id, timestamp)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_channel_guidelines_guild ON channel_guidelines(guild_id)")
        
        # Strategic indexes for moderation_actions table
        await db.execute("CREATE INDEX IF NOT EXISTS idx_moderation_actions_timestamp ON moderation_actions(timestamp DESC)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_moderation_actions_user ON moderation_actions(user_id, guild_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_moderation_actions_action ON moderation_actions(action, guild_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_moderation_actions_bulk ON moderation_actions(guild_id, timestamp DESC, user_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_moderation_actions_channel ON moderation_actions(channel_id, timestamp DESC)")
    
    @staticmethod
    async def _create_triggers(db: aiosqlite.Connection) -> None:
        """Create triggers for automatic timestamp updates."""
        await db.execute("""
            CREATE TRIGGER IF NOT EXISTS update_guild_settings_timestamp
            AFTER UPDATE ON guild_settings
            FOR EACH ROW
            BEGIN
                UPDATE guild_settings SET updated_at = CURRENT_TIMESTAMP
                WHERE guild_id = NEW.guild_id;
            END
        """)
        
        await db.execute("""
            CREATE TRIGGER IF NOT EXISTS update_channel_guidelines_timestamp
            AFTER UPDATE ON channel_guidelines
            FOR EACH ROW
            BEGIN
                UPDATE channel_guidelines SET updated_at = CURRENT_TIMESTAMP
                WHERE guild_id = NEW.guild_id AND channel_id = NEW.channel_id;
            END
        """)
    
    @staticmethod
    async def _update_schema_version(db: aiosqlite.Connection) -> None:
        """Update schema version tracking."""
        await db.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (2)")
