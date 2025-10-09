import unittest
from unittest.mock import Mock, patch, AsyncMock
import discord

from modcord.util.discord_utils import (
    PERMANENT_DURATION,
    build_dm_message,
    format_duration,
    is_ignored_author,
    has_elevated_permissions,
    parse_duration_to_seconds,
    has_permissions,
    send_dm_to_user,
    safe_delete_message,
)
from modcord.util.moderation_datatypes import ActionType


class DiscordUtilsPermissionTests(unittest.TestCase):
    def test_is_ignored_author(self):
        # Create a mock for a bot user
        bot_user = Mock(spec=discord.User)
        bot_user.bot = True
        self.assertTrue(is_ignored_author(bot_user))

        # Create a mock for a non-bot member
        member = Mock(spec=discord.Member)
        member.bot = False
        self.assertFalse(is_ignored_author(member))

        # Create a mock for a non-member user
        user = Mock(spec=discord.User)
        user.bot = False
        self.assertTrue(is_ignored_author(user))

    def test_has_elevated_permissions(self):
        # Test with a member that has no elevated permissions
        member_no_perms = Mock(spec=discord.Member)
        member_no_perms.guild_permissions.administrator = False
        member_no_perms.guild_permissions.manage_guild = False
        member_no_perms.guild_permissions.moderate_members = False
        self.assertFalse(has_elevated_permissions(member_no_perms))

        # Test with a member that has administrator permissions
        member_admin = Mock(spec=discord.Member)
        member_admin.guild_permissions.administrator = True
        self.assertTrue(has_elevated_permissions(member_admin))

        # Test with a non-member user
        user = Mock(spec=discord.User)
        self.assertFalse(has_elevated_permissions(user))

    def test_has_permissions(self):
        # Mock context with a non-member author
        ctx_non_member = Mock(spec=discord.ApplicationContext)
        ctx_non_member.author = Mock(spec=discord.User)
        self.assertFalse(has_permissions(ctx_non_member, manage_messages=True))

        # Mock context with a member author
        ctx_member = Mock(spec=discord.ApplicationContext)
        ctx_member.author = Mock(spec=discord.Member)

        # No permissions required
        self.assertTrue(has_permissions(ctx_member))

        # Single permission check - has permission
        ctx_member.author.guild_permissions.manage_messages = True
        self.assertTrue(has_permissions(ctx_member, manage_messages=True))

        # Single permission check - does not have permission
        ctx_member.author.guild_permissions.kick_members = False
        self.assertFalse(has_permissions(ctx_member, kick_members=True))

        # Multiple permissions check - has all
        ctx_member.author.guild_permissions.manage_messages = True
        ctx_member.author.guild_permissions.kick_members = True
        self.assertTrue(has_permissions(ctx_member, manage_messages=True, kick_members=True))

        # Multiple permissions check - has some but not all
        ctx_member.author.guild_permissions.manage_messages = True
        ctx_member.author.guild_permissions.kick_members = False
        self.assertFalse(has_permissions(ctx_member, manage_messages=True, kick_members=True))


class DiscordUtilsFormattingTests(unittest.TestCase):
    def test_format_duration_handles_special_cases(self) -> None:
        self.assertEqual(format_duration(0), PERMANENT_DURATION)
        self.assertEqual(format_duration(45), "45 secs")
        self.assertEqual(format_duration(120), "2 mins")
        self.assertEqual(format_duration(3600), "1 hour")
        self.assertEqual(format_duration(90000), "1 day")

    def test_parse_duration_to_seconds_known_values(self) -> None:
        self.assertEqual(parse_duration_to_seconds("60 secs"), 60)
        self.assertEqual(parse_duration_to_seconds("1 week"), 7 * 24 * 60 * 60)
        self.assertEqual(parse_duration_to_seconds("Till the end of time"), 0)
        # Unknown labels should fall back to zero seconds
        self.assertEqual(parse_duration_to_seconds("unknown"), 0)


class DiscordUtilsDmMessageTests(unittest.TestCase):
    def test_build_dm_message_for_ban(self) -> None:
        message = build_dm_message(ActionType.BAN, "Guild", "Rule violation", "2 hours")
        self.assertIn("banned from Guild for 2 hours", message)
        self.assertIn("Rule violation", message)

    def test_build_dm_message_for_permanent_ban(self) -> None:
        message = build_dm_message(ActionType.BAN, "Guild", "Rule violation", PERMANENT_DURATION)
        self.assertIn("permanently", message.lower())

    def test_build_dm_message_for_warn(self) -> None:
        message = build_dm_message(ActionType.WARN, "Guild", "Be kind")
        self.assertIn("warning", message.lower())
        self.assertIn("Be kind", message)


if __name__ == "__main__":  # pragma: no cover - direct invocation guard
    unittest.main()


class DiscordUtilsAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_send_dm_to_user(self):
        # Mock a user that can receive DMs
        target_user_success = AsyncMock(spec=discord.Member)
        self.assertTrue(await send_dm_to_user(target_user_success, "Test message"))
        target_user_success.send.assert_called_once_with("Test message")

        # Mock a user that cannot receive DMs (raises Forbidden)
        target_user_fail = AsyncMock(spec=discord.Member)
        target_user_fail.send.side_effect = discord.Forbidden(Mock(), "Cannot send DMs")
        self.assertFalse(await send_dm_to_user(target_user_fail, "Test message"))

    async def test_safe_delete_message(self):
        # Mock a message that can be deleted successfully
        message_success = AsyncMock(spec=discord.Message)
        self.assertTrue(await safe_delete_message(message_success))
        message_success.delete.assert_called_once()

        # Mock a message that is not found
        message_not_found = AsyncMock(spec=discord.Message)
        message_not_found.delete.side_effect = discord.NotFound(Mock(), "Unknown Message")
        self.assertFalse(await safe_delete_message(message_not_found))

        # Mock a message where deletion is forbidden
        message_forbidden = AsyncMock(spec=discord.Message)
        message_forbidden.delete.side_effect = discord.Forbidden(Mock(), "Missing Permissions")
        self.assertFalse(await safe_delete_message(message_forbidden))
