import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import discord
from modcord.util.actions import ActionType
from modcord.bot import bot_helper


class TestBotHelper(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        await bot_helper.reset_unban_scheduler_for_tests()

    def test_parse_duration_to_seconds(self):
        self.assertEqual(bot_helper.parse_duration_to_seconds("60 secs"), 60)
        self.assertEqual(bot_helper.parse_duration_to_seconds("5 mins"), 300)
        self.assertEqual(bot_helper.parse_duration_to_seconds("1 hour"), 3600)
        self.assertEqual(bot_helper.parse_duration_to_seconds("1 day"), 86400)
        self.assertEqual(bot_helper.parse_duration_to_seconds("1 week"), 604800)
        self.assertEqual(bot_helper.parse_duration_to_seconds(bot_helper.PERMANENT_DURATION), 0)
        self.assertEqual(bot_helper.parse_duration_to_seconds("invalid duration"), 0)

    def test_has_permissions(self):
        mock_ctx = MagicMock(spec=discord.ApplicationContext)
        mock_member = MagicMock(spec=discord.Member)

        # Test with permissions
        mock_member.guild_permissions.ban_members = True
        mock_member.guild_permissions.kick_members = True
        mock_ctx.author = mock_member
        self.assertTrue(bot_helper.has_permissions(mock_ctx, ban_members=True, kick_members=True))

        # Test without permissions
        mock_member.guild_permissions.ban_members = False
        self.assertFalse(bot_helper.has_permissions(mock_ctx, ban_members=True))

        # Test with a non-member author
        mock_ctx.author = MagicMock(spec=discord.User)
        self.assertFalse(bot_helper.has_permissions(mock_ctx, ban_members=True))

    async def test_send_dm_to_user(self):
        mock_user = MagicMock(spec=discord.Member)
        mock_user.send = AsyncMock()

        # Test success
        result = await bot_helper.send_dm_to_user(mock_user, "test message")
        self.assertTrue(result)
        mock_user.send.assert_called_once_with("test message")

        # Test failure (Forbidden)
        mock_user.send.reset_mock()
        mock_user.send.side_effect = discord.Forbidden(MagicMock(), "DM disabled")
        result = await bot_helper.send_dm_to_user(mock_user, "test message")
        self.assertFalse(result)
        mock_user.send.assert_called_once_with("test message")

    async def test_create_punishment_embed(self):
        mock_user = MagicMock(spec=discord.User)
        mock_user.mention = "@testuser"
        mock_user.id = 12345
        mock_issuer = MagicMock(spec=discord.User)
        mock_issuer.mention = "@moderator"
        mock_bot_user = MagicMock(spec=discord.ClientUser)
        mock_bot_user.name = "TestBot"

        embed = await bot_helper.create_punishment_embed(
            action_type=ActionType.BAN,
            user=mock_user,
            reason="Test reason",
            duration_str="1 hour",
            issuer=mock_issuer,
            bot_user=mock_bot_user
        )

        self.assertEqual(embed.title, "🔨 Ban Issued")
        self.assertEqual(embed.color, discord.Color.red())
        self.assertEqual(len(embed.fields), 5)
        self.assertEqual(embed.fields[0].name, "User")
        self.assertEqual(embed.fields[0].value, "@testuser (`12345`)")
        self.assertEqual(embed.fields[2].name, "Moderator")
        self.assertEqual(embed.fields[2].value, "@moderator")
        self.assertEqual(embed.fields[4].name, "Duration")
        self.assertIn("1 hour", embed.fields[4].value)


    @patch('src.modcord.bot_helper.send_dm_to_user', new_callable=AsyncMock)
    @patch('src.modcord.bot_helper.create_punishment_embed', new_callable=AsyncMock)
    async def test_take_action_ban(self, mock_create_embed, mock_send_dm):
        mock_message = MagicMock(spec=discord.Message)
        mock_message.author = MagicMock(spec=discord.Member)
        mock_message.guild = MagicMock(spec=discord.Guild)
        mock_message.guild.ban = AsyncMock()
        mock_message.delete = AsyncMock()
        mock_bot_user = MagicMock(spec=discord.ClientUser)

        await bot_helper.take_action(ActionType.BAN, "Test ban reason", mock_message, mock_bot_user)

        mock_message.guild.ban.assert_called_once_with(mock_message.author, reason="AI Mod: Test ban reason")
        mock_send_dm.assert_called_once()
        mock_create_embed.assert_called_once()
        mock_message.delete.assert_called_once()

    @patch('src.modcord.bot_helper.send_dm_to_user', new_callable=AsyncMock)
    @patch('src.modcord.bot_helper.create_punishment_embed', new_callable=AsyncMock)
    async def test_take_action_warn(self, mock_create_embed, mock_send_dm):
        mock_message = MagicMock(spec=discord.Message)
        mock_message.author = MagicMock(spec=discord.Member)
        mock_message.guild = MagicMock(spec=discord.Guild)
        mock_bot_user = MagicMock(spec=discord.ClientUser)

        await bot_helper.take_action(ActionType.WARN, "Test warn reason", mock_message, mock_bot_user)

        mock_send_dm.assert_called_once()
        mock_create_embed.assert_called_once()

    async def test_take_action_delete(self):
        mock_message = MagicMock(spec=discord.Message)
        mock_message.author = MagicMock(spec=discord.Member)
        mock_message.guild = MagicMock(spec=discord.Guild)
        mock_message.delete = AsyncMock()
        mock_bot_user = MagicMock(spec=discord.ClientUser)

        await bot_helper.take_action(ActionType.DELETE, "Test delete reason", mock_message, mock_bot_user)

        mock_message.delete.assert_called_once()

    @patch('src.modcord.bot_helper.create_punishment_embed', new_callable=AsyncMock)
    async def test_schedule_unban_immediate(self, mock_create_embed):
        guild = MagicMock(spec=discord.Guild)
        guild.id = 123
        guild.unban = AsyncMock()
        channel = MagicMock(spec=discord.TextChannel)
        channel.send = AsyncMock()
        bot = MagicMock()
        bot.fetch_user = AsyncMock(return_value=MagicMock(spec=discord.User))
        bot.user = MagicMock(spec=discord.ClientUser)
        mock_create_embed.return_value = MagicMock()

        await bot_helper.schedule_unban(guild, 555, channel, 0, bot)

        self.assertEqual(guild.unban.await_count, 1)
        args, _ = guild.unban.await_args
        self.assertEqual(args[0].id, 555)
        bot.fetch_user.assert_awaited_once_with(555)
        channel.send.assert_awaited_once_with(embed=mock_create_embed.return_value)

    @patch('src.modcord.bot_helper.create_punishment_embed', new_callable=AsyncMock)
    async def test_schedule_unban_delayed(self, mock_create_embed):
        guild = MagicMock(spec=discord.Guild)
        guild.id = 321
        guild.unban = AsyncMock()
        channel = MagicMock(spec=discord.TextChannel)
        channel.send = AsyncMock()
        bot = MagicMock()
        bot.fetch_user = AsyncMock(return_value=MagicMock(spec=discord.User))
        bot.user = MagicMock(spec=discord.ClientUser)
        mock_create_embed.return_value = MagicMock()

        await bot_helper.schedule_unban(guild, 777, channel, 0.05, bot)
        await asyncio.sleep(0.1)

        self.assertEqual(guild.unban.await_count, 1)
        self.assertGreaterEqual(bot.fetch_user.await_count, 1)
        self.assertGreaterEqual(channel.send.await_count, 1)

    @patch('src.modcord.bot_helper.create_punishment_embed', new_callable=AsyncMock)
    async def test_schedule_unban_replaces_existing(self, mock_create_embed):
        guild = MagicMock(spec=discord.Guild)
        guild.id = 999
        guild.unban = AsyncMock()
        channel = MagicMock(spec=discord.TextChannel)
        channel.send = AsyncMock()
        bot = MagicMock()
        bot.fetch_user = AsyncMock(return_value=MagicMock(spec=discord.User))
        bot.user = MagicMock(spec=discord.ClientUser)
        mock_create_embed.return_value = MagicMock()

        await bot_helper.schedule_unban(guild, 888, channel, 0.2, bot)
        await bot_helper.schedule_unban(guild, 888, channel, 0.05, bot)
        await asyncio.sleep(0.12)

        self.assertEqual(guild.unban.await_count, 1)
        self.assertEqual(bot.fetch_user.await_count, 1)
        self.assertEqual(channel.send.await_count, 1)

if __name__ == "__main__":
    unittest.main()
