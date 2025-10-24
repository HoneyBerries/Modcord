"""
Bot settings: persistent per-guild flags and runtime batching.

Responsibilities:
- Persist per-guild settings (ai_enabled, rules, and action toggles) to SQLite database
- Cache server rules and per-channel chat history
- Provide a 15s channel message batching mechanism with an async callback

Database schema:
- guild_settings table with columns: guild_id, ai_enabled, rules, auto_*_enabled flags
"""

import collections
import asyncio
import discord
from typing import Dict, DefaultDict, Callable, Awaitable, Optional, List, Sequence, Set
from dataclasses import dataclass
from modcord.util.logger import get_logger
from modcord.moderation.moderation_datatypes import ActionType, ModerationChannelBatch, ModerationMessage, ModerationUser
from modcord.history.history_cache import global_history_cache_manager
from modcord.configuration.app_configuration import app_config
from modcord.database.database import init_database, get_connection

logger = get_logger("guild_settings_manager")


@dataclass(slots=True)
class GuildSettings:
    """Persistent per-guild configuration along with transient batching state."""

    guild_id: int
    ai_enabled: bool = True
    rules: str = ""
    auto_warn_enabled: bool = True
    auto_delete_enabled: bool = True
    auto_timeout_enabled: bool = True
    auto_kick_enabled: bool = True
    auto_ban_enabled: bool = True


ACTION_FLAG_FIELDS: dict[ActionType, str] = {
    ActionType.WARN: "auto_warn_enabled",
    ActionType.DELETE: "auto_delete_enabled",
    ActionType.TIMEOUT: "auto_timeout_enabled",
    ActionType.KICK: "auto_kick_enabled",
    ActionType.BAN: "auto_ban_enabled",
}


class GuildSettingsManager:
    """
    Manager for persistent per-guild settings and transient state.

    Responsibilities:
    - Persist per-guild settings (ai_enabled, rules, action toggles) to SQLite database
    - Cache server rules and per-channel chat history
    - Provide a config-driven global message batching window with an async callback
    """

    def __init__(self):
        """Instantiate caches, batching queues, and persistence helpers."""
        # Persisted guild settings registry (guild_id -> GuildSettings)
        self.guilds: Dict[int, GuildSettings] = {}

        # Channel-specific guidelines cache (guild_id -> channel_id -> guidelines_text)
        self.channel_guidelines: DefaultDict[int, Dict[int, str]] = collections.defaultdict(dict)

        # Global message batching system
        self.channel_message_batches: DefaultDict[int, List[ModerationMessage]] = collections.defaultdict(list)
        self.global_batch_timer: Optional[asyncio.Task] = None
        self.batch_processing_callback: Optional[Callable[[List[ModerationChannelBatch]], Awaitable[None]]] = None
        self._batch_lock = asyncio.Lock()
        
        # Bot instance for fetching member information
        self.bot_instance = None

        # Persistence helpers
        self._persist_lock = asyncio.Lock()
        self._active_persists: Set[asyncio.Task] = set()
        self._db_initialized = False

        # Initialize database and load settings asynchronously
        # This will be called from an async context during bot startup
        logger.info("Guild settings manager initialized")

    async def async_init(self) -> None:
        """Initialize the database and load settings from disk (async)."""
        if not self._db_initialized:
            await init_database()
            await self.load_from_disk()
            self._db_initialized = True
            logger.info("Database initialized and settings loaded")

    def ensure_guild(self, guild_id: int) -> GuildSettings:
        """Create default settings for a guild if none exist and return the record."""
        settings = self.guilds.get(guild_id)
        if settings is None:
            settings = GuildSettings(guild_id=guild_id)
            self.guilds[guild_id] = settings
        return settings

    def get_guild_settings(self, guild_id: int) -> GuildSettings:
        """Fetch the cached :class:`GuildSettings` instance for the given guild."""
        return self.ensure_guild(guild_id)

    def list_guild_ids(self) -> List[int]:
        """Return a snapshot list of guild IDs currently cached in memory."""
        return list(self.guilds.keys())

    def get_server_rules(self, guild_id: int) -> str:
        """Return cached rules for a guild or an empty string."""
        settings = self.guilds.get(guild_id)
        return settings.rules if settings else ""

    def set_server_rules(self, guild_id: int, rules: str) -> None:
        """
        Cache and persist rules for the given guild.

        Persistence is scheduled in a non-blocking manner.
        """
        if rules is None:
            rules = ""

        settings = self.ensure_guild(guild_id)
        settings.rules = rules
        logger.debug(f"Updated rules cache for guild {guild_id} (len={len(rules)})")

        self._trigger_persist(guild_id)

    def get_channel_guidelines(self, guild_id: int, channel_id: int) -> str:
        """Return cached channel-specific guidelines or an empty string."""
        return self.channel_guidelines.get(guild_id, {}).get(channel_id, "")

    def set_channel_guidelines(self, guild_id: int, channel_id: int, guidelines: str) -> None:
        """
        Cache and persist channel-specific guidelines.

        Persistence is scheduled in a non-blocking manner.
        """
        if guidelines is None:
            guidelines = ""

        if guild_id not in self.channel_guidelines:
            self.channel_guidelines[guild_id] = {}
        
        self.channel_guidelines[guild_id][channel_id] = guidelines
        logger.debug(
            f"Updated channel guidelines cache for guild {guild_id}, channel {channel_id} (len={len(guidelines)})"
        )

        self._trigger_persist_channel_guidelines(guild_id, channel_id)

    # --- Global message batching system ---
    def set_bot_instance(self, bot_instance) -> None:
        """Set the bot instance for fetching member information."""
        self.bot_instance = bot_instance
        logger.info("Bot instance set for guild settings manager")
    
    def set_batch_processing_callback(self, callback: Callable[[List[ModerationChannelBatch]], Awaitable[None]]) -> None:
        """Set the async callback invoked when global batches are ready."""
        self.batch_processing_callback = callback
        logger.info("Batch processing callback set")

    async def _group_messages_by_user(
        self, 
        messages: List[ModerationMessage],
        bot_instance
    ) -> List[ModerationUser]:
        """Group messages by user_id and create ModerationUser objects with role information.
        
        Parameters
        ----------
        messages:
            List of messages to group by user.
        bot_instance:
            Discord bot instance to fetch member information for roles and join_date.
            
        Returns
        -------
        List[ModerationUser]
            List of users with their messages, ordered by first message appearance.
        """
        import datetime
        
        # Group messages by user_id
        user_messages: Dict[str, List[ModerationMessage]] = collections.defaultdict(list)
        first_appearance: Dict[str, int] = {}
        
        for idx, msg in enumerate(messages):
            user_id = str(msg.user_id)
            if user_id not in first_appearance:
                first_appearance[user_id] = idx
            user_messages[user_id].append(msg)
        
        # Create ModerationUser objects
        moderation_users: List[ModerationUser] = []
        
        for user_id, user_msgs in user_messages.items():
            # Get user information from first message with discord_message reference
            discord_msg = next((m.discord_message for m in user_msgs if m.discord_message), None)
            
            username = "Unknown User"
            roles: List[str] = []
            join_date: Optional[str] = None
            
            if discord_msg and discord_msg.guild and discord_msg.author:
                username = str(discord_msg.author)
                
                # Get member to access roles and join date
                if isinstance(discord_msg.author, discord.Member):
                    member = discord_msg.author
                    # Extract role names (excluding @everyone)
                    roles = [role.name for role in member.roles if role.name != "@everyone"]
                    
                    # Get join date
                    if member.joined_at:
                        join_date = member.joined_at.astimezone(
                            datetime.timezone.utc
                        ).replace(microsecond=0).isoformat().replace('+00:00', 'Z')
            
            mod_user = ModerationUser(
                user_id=user_id,
                username=username,
                roles=roles,
                join_date=join_date,
                messages=user_msgs,
            )
            moderation_users.append(mod_user)
        
        # Sort users by first appearance
        moderation_users.sort(key=lambda u: first_appearance[u.user_id])
        
        return moderation_users

    async def add_message_to_batch(self, channel_id: int, message: ModerationMessage) -> None:
        """Queue a message for global batch processing and start timer if needed."""
        async with self._batch_lock:
            self.channel_message_batches[channel_id].append(message)
            logger.debug(
                "Added message to batch for channel %s, current batch size: %d",
                channel_id,
                len(self.channel_message_batches[channel_id]),
            )

            if self.global_batch_timer is None or self.global_batch_timer.done():
                self.global_batch_timer = asyncio.create_task(self.global_batch_timer_task())
                logger.debug("Started global batch timer")

    async def global_batch_timer_task(self) -> None:
        """Global timer that processes all pending channel batches together."""
        try:
            ai_settings = app_config.ai_settings if app_config else {}
            moderation_batch_seconds = float(ai_settings.get("moderation_batch_seconds", 10.0))
            logger.debug("Global batch timer started with %s seconds", moderation_batch_seconds)
            await asyncio.sleep(moderation_batch_seconds)

            async with self._batch_lock:
                pending_batches = {
                    channel_id: list(messages)
                    for channel_id, messages in self.channel_message_batches.items()
                    if messages
                }
                # Reset container for next window
                self.channel_message_batches = collections.defaultdict(list)

            channel_batches: List[ModerationChannelBatch] = []
            for channel_id, messages in pending_batches.items():
                # Group messages by user
                users = await self._group_messages_by_user(messages, self.bot_instance)
                
                # Get history context and group by user as well
                history_messages = await self._resolve_history_context(channel_id, messages)
                history_users = await self._group_messages_by_user(history_messages, self.bot_instance) if history_messages else []
                
                channel_batches.append(
                    ModerationChannelBatch(
                        channel_id=channel_id,
                        users=users,
                        history_users=history_users,
                    )
                )
                
                total_messages = sum(len(user.messages) for user in users)
                total_history = sum(len(user.messages) for user in history_users)
                logger.debug(
                    "Prepared batch for channel %s: %d users (%d messages), %d history users (%d messages)",
                    channel_id,
                    len(users),
                    total_messages,
                    len(history_users),
                    total_history,
                )

            if channel_batches and self.batch_processing_callback:
                total_users = sum(len(b.users) for b in channel_batches)
                total_msgs = sum(sum(len(u.messages) for u in b.users) for b in channel_batches)
                logger.debug(
                    "Processing global batch: %d channels, %d total users, %d total messages",
                    len(channel_batches),
                    total_users,
                    total_msgs,
                )
                try:
                    await self.batch_processing_callback(channel_batches)
                except Exception:
                    logger.exception("Exception while processing global batch")
            else:
                logger.debug("No batches or callback to process")

        except asyncio.CancelledError:
            logger.info("Global batch timer cancelled")
        except Exception:
            logger.exception("Error in global batch timer")
        finally:
            self.global_batch_timer = None

    def cancel_all_batch_timers(self) -> None:
        """
        Cancel the global batch timer (use during shutdown).

        This is synchronous and will request cancellation; call shutdown() to
        await the task and ensure cleanup.
        """
        if self.global_batch_timer and not self.global_batch_timer.done():
            self.global_batch_timer.cancel()
        self.global_batch_timer = None
        logger.info("Requested cancellation of global batch timer")

    def _trigger_persist(self, guild_id: int) -> None:
        """Schedule a best-effort persist of a single guild's settings to database."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("Cannot persist guild %s: no running event loop", guild_id)
            return

        task = loop.create_task(self._persist_guild_async(guild_id))
        self._active_persists.add(task)

        def _cleanup(completed: asyncio.Task) -> None:
            self._active_persists.discard(completed)
            try:
                if not completed.result():
                    logger.error("Failed to persist guild %s to database", guild_id)
            except Exception:
                logger.exception("Error while persisting guild %s to database", guild_id)

        task.add_done_callback(_cleanup)

    def _trigger_persist_channel_guidelines(self, guild_id: int, channel_id: int) -> None:
        """Schedule a best-effort persist of channel guidelines to database."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning(
                "Cannot persist channel guidelines for guild %s, channel %s: no running event loop",
                guild_id,
                channel_id
            )
            return

        task = loop.create_task(self._persist_channel_guidelines_async(guild_id, channel_id))
        self._active_persists.add(task)

        def _cleanup(completed: asyncio.Task) -> None:
            self._active_persists.discard(completed)
            try:
                if not completed.result():
                    logger.error(
                        "Failed to persist channel guidelines for guild %s, channel %s",
                        guild_id,
                        channel_id
                    )
            except Exception:
                logger.exception(
                    "Error while persisting channel guidelines for guild %s, channel %s",
                    guild_id,
                    channel_id
                )

        task.add_done_callback(_cleanup)

    async def _resolve_history_context(
        self,
        channel_id: int,
        current_batch: Sequence[ModerationMessage],
    ) -> List[ModerationMessage]:
        """Select prior channel messages to provide as model context.
        
        Uses the message cache and Discord API fallback to fetch historical
        context, ensuring availability even if the bot was offline when
        messages were posted.
        """
        # Build set of message IDs to exclude (current batch)
        current_ids = {str(msg.message_id) for msg in current_batch}

        # Use a default or config-driven value for history context length, or make it a parameter if needed
        default_limit = 20  # You can make this configurable elsewhere if desired
        try:
            history_messages = await global_history_cache_manager.fetch_history_for_context(
                channel_id,
                limit=default_limit,
                exclude_message_ids=current_ids,
            )
            if history_messages:
                logger.debug(
                    "Resolved %d history messages for channel %s from cache/API",
                    len(history_messages),
                    channel_id,
                )
            return history_messages
        except Exception as exc:
            logger.warning(
                "Error fetching history context for channel %s: %s",
                channel_id,
                exc,
            )
            return []

    async def shutdown(self) -> None:
        """Gracefully cancel and await the global batch timer (await on shutdown)."""
        if self.global_batch_timer and not self.global_batch_timer.done():
            self.global_batch_timer.cancel()
            try:
                await self.global_batch_timer
            except asyncio.CancelledError:
                pass
        self.global_batch_timer = None

        self.channel_message_batches.clear()

        pending = list(self._active_persists)
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        self._active_persists.clear()

        logger.info("Shutdown complete: batch timer cleared")
        logger.info("--------------------------------------------------------------------------------")

    # --- AI moderation enable/disable ---
    def is_ai_enabled(self, guild_id: int) -> bool:
        """Return True if AI moderation is enabled for the guild (default True)."""
        settings = self.guilds.get(guild_id)
        return settings.ai_enabled if settings else True

    def set_ai_enabled(self, guild_id: int, enabled: bool) -> bool:
        """
        Set and persist the AI moderation enabled state for a guild.
        Return whether scheduling the persist was successful or not.
        """
        settings = self.ensure_guild(guild_id)
        settings.ai_enabled = bool(enabled)
        state = "enabled" if enabled else "disabled"
        logger.debug("AI moderation %s for guild %s", state, guild_id)
        self._trigger_persist(guild_id)
        return True

    def is_action_allowed(self, guild_id: int, action: ActionType) -> bool:
        """Return whether the specified AI action is allowed for the guild."""
        settings = self.ensure_guild(guild_id)
        field_name = ACTION_FLAG_FIELDS.get(action)
        if field_name is None:
            return True
        return bool(getattr(settings, field_name, True))
    

    def set_action_allowed(self, guild_id: int, action: ActionType, enabled: bool) -> bool:
        """Enable or disable an AI action for the guild and persist the change."""
        field_name = ACTION_FLAG_FIELDS.get(action)
        if field_name is None:
            logger.warning("Attempted to toggle unsupported action %s for guild %s", action, guild_id)
            return False

        settings = self.ensure_guild(guild_id)
        setattr(settings, field_name, bool(enabled))
        logger.debug(
            "Set %s to %s for guild %s",
            field_name,
            enabled,
            guild_id,
        )
        self._trigger_persist(guild_id)
        return True

    # --- Persistence helpers ---
    async def _persist_guild_async(self, guild_id: int) -> bool:
        """
        Persist a single guild's settings to the database asynchronously.

        Args:
            guild_id: The guild ID to persist

        Returns:
            bool: True if successful, False otherwise
        """
        settings = self.guilds.get(guild_id)
        if settings is None:
            logger.warning("Cannot persist guild %s: not in cache", guild_id)
            return False

        async with self._persist_lock:
            try:
                async with get_connection() as db:
                    await db.execute("""
                        INSERT INTO guild_settings (
                            guild_id, ai_enabled, rules,
                            auto_warn_enabled, auto_delete_enabled,
                            auto_timeout_enabled, auto_kick_enabled, auto_ban_enabled
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(guild_id) DO UPDATE SET
                            ai_enabled = excluded.ai_enabled,
                            rules = excluded.rules,
                            auto_warn_enabled = excluded.auto_warn_enabled,
                            auto_delete_enabled = excluded.auto_delete_enabled,
                            auto_timeout_enabled = excluded.auto_timeout_enabled,
                            auto_kick_enabled = excluded.auto_kick_enabled,
                            auto_ban_enabled = excluded.auto_ban_enabled
                    """, (
                        guild_id,
                        1 if settings.ai_enabled else 0,
                        settings.rules,
                        1 if settings.auto_warn_enabled else 0,
                        1 if settings.auto_delete_enabled else 0,
                        1 if settings.auto_timeout_enabled else 0,
                        1 if settings.auto_kick_enabled else 0,
                        1 if settings.auto_ban_enabled else 0,
                    ))
                    await db.commit()
                    logger.debug("Persisted guild %s to database", guild_id)
                    return True
            except Exception:
                logger.exception("Failed to persist guild %s to database", guild_id)
                return False

    async def _persist_channel_guidelines_async(self, guild_id: int, channel_id: int) -> bool:
        """
        Persist channel-specific guidelines to the database asynchronously.

        Args:
            guild_id: The guild ID
            channel_id: The channel ID

        Returns:
            bool: True if successful, False otherwise
        """
        guidelines = self.channel_guidelines.get(guild_id, {}).get(channel_id)
        if guidelines is None:
            logger.warning(
                "Cannot persist channel guidelines for guild %s, channel %s: not in cache",
                guild_id,
                channel_id
            )
            return False

        async with self._persist_lock:
            try:
                async with get_connection() as db:
                    await db.execute("""
                        INSERT INTO channel_guidelines (guild_id, channel_id, guidelines)
                        VALUES (?, ?, ?)
                        ON CONFLICT(guild_id, channel_id) DO UPDATE SET
                            guidelines = excluded.guidelines
                    """, (guild_id, channel_id, guidelines))
                    await db.commit()
                    logger.debug(
                        "Persisted channel guidelines for guild %s, channel %s to database",
                        guild_id,
                        channel_id
                    )
                    return True
            except Exception:
                logger.exception(
                    "Failed to persist channel guidelines for guild %s, channel %s to database",
                    guild_id,
                    channel_id
                )
                return False

    async def load_from_disk(self) -> bool:
        """Load persisted guild settings from database into memory."""
        try:
            async with get_connection() as db:
                # Load guild settings
                async with db.execute("SELECT * FROM guild_settings") as cursor:
                    rows = await cursor.fetchall()
                    
                self.guilds.clear()
                for row in rows:
                    guild_id = row[0]
                    self.guilds[guild_id] = GuildSettings(
                        guild_id=guild_id,
                        ai_enabled=bool(row[1]),
                        rules=row[2],
                        auto_warn_enabled=bool(row[3]),
                        auto_delete_enabled=bool(row[4]),
                        auto_timeout_enabled=bool(row[5]),
                        auto_kick_enabled=bool(row[6]),
                        auto_ban_enabled=bool(row[7]),
                    )
                
                # Load channel guidelines
                async with db.execute("SELECT guild_id, channel_id, guidelines FROM channel_guidelines") as cursor:
                    guidelines_rows = await cursor.fetchall()
                
                self.channel_guidelines.clear()
                for row in guidelines_rows:
                    guild_id = row[0]
                    channel_id = row[1]
                    guidelines = row[2]
                    
                    if guild_id not in self.channel_guidelines:
                        self.channel_guidelines[guild_id] = {}
                    self.channel_guidelines[guild_id][channel_id] = guidelines
                
                if rows:
                    logger.info("Loaded %d guild settings from database", len(list(rows)))
                if guidelines_rows:
                    logger.info("Loaded %d channel guidelines from database", len(list(guidelines_rows)))
                
                return bool(rows or guidelines_rows)
        except Exception:
            logger.exception("Failed to load guild settings from database")
            return False

    async def persist_guild(self, guild_id: int) -> bool:
        """
        Persist a single guild's settings to database asynchronously.

        Return whether the write was successful or not.

        This version performs only asynchronous writes. Callers must invoke
        and await this coroutine from an active event loop.
        """
        return await self._persist_guild_async(guild_id)


# Global guild settings manager instance
guild_settings_manager = GuildSettingsManager()