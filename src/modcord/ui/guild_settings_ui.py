import datetime
import discord
from discord.ext import commands

from modcord.datatypes.action_datatypes import ActionType
from modcord.datatypes.discord_datatypes import GuildID, ChannelID
from modcord.datatypes.guild_settings import GuildSettings, ACTION_FLAG_FIELDS
from modcord.settings.guild_settings_manager import guild_settings_manager

# Action constants
ACTION_UI_ORDER = (
    ActionType.WARN,
    ActionType.DELETE,
    ActionType.TIMEOUT,
    ActionType.KICK,
    ActionType.BAN,
)

ACTION_UI_LABELS = {
    ActionType.WARN: "Warn",
    ActionType.DELETE: "Delete",
    ActionType.TIMEOUT: "Timeout",
    ActionType.KICK: "Kick",
    ActionType.BAN: "Ban",
}

ACTION_UI_EMOJIS = {
    ActionType.WARN: "⚠️",
    ActionType.DELETE: "🗑️",
    ActionType.TIMEOUT: "⏲️",
    ActionType.KICK: "👢",
    ActionType.BAN: "🔨",
}

# ──────────────────────────────────────────────
# Embed builder
# ──────────────────────────────────────────────
def build_full_settings_embed(settings: GuildSettings) -> discord.Embed:
    ai_status = "Enabled ✅" if settings.ai_enabled else "Disabled ❌"
    actions_text = "\n".join(
        f"{ACTION_UI_EMOJIS[a]} **{ACTION_UI_LABELS[a]}** — {'✅' if getattr(settings, ACTION_FLAG_FIELDS[a], True) else '❌'}"
        for a in ACTION_UI_ORDER
    )
    modlog = f"<#{int(settings.mod_log_channel_id)}>" if settings.mod_log_channel_id else "Not configured"

    embed = discord.Embed(
        title="Server Moderation Settings",
        description="All moderation settings for this server in one embed.",
        color=discord.Color.blurple(),
        timestamp=datetime.datetime.now(datetime.timezone.utc),
    )
    embed.add_field(name="AI Moderation", value=ai_status, inline=False)
    embed.add_field(name="Automatic Actions", value=actions_text, inline=False)
    embed.add_field(name="AutoMod Log Channel", value=modlog, inline=False)
    embed.set_footer(text="Use the buttons below to modify settings interactively.")
    return embed

# ──────────────────────────────────────────────
# Views (interactive buttons)
# ──────────────────────────────────────────────
class FullSettingsView(discord.ui.View):
    """Single view for AI, actions, and modlog with buttons/selects."""

    def __init__(self, guild_id: GuildID, settings: GuildSettings):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.settings = settings

        # AI toggle (row 0)
        self.ai_button = discord.ui.Button(
            label="Disable AI" if settings.ai_enabled else "Enable AI",
            style=discord.ButtonStyle.red if settings.ai_enabled else discord.ButtonStyle.success,
            emoji="🤖",
            row=0,
        )
        self.ai_button.callback = self.toggle_ai
        self.add_item(self.ai_button)

        # Action buttons (on row 1, all 5 fit in one row)
        self.action_buttons = {}
        for i, action in enumerate(ACTION_UI_ORDER):
            enabled = getattr(settings, ACTION_FLAG_FIELDS[action], True)
            btn = discord.ui.Button(
                label=f"{ACTION_UI_EMOJIS[action]} {ACTION_UI_LABELS[action]} {'✅' if enabled else '❌'}",
                style=discord.ButtonStyle.success if enabled else discord.ButtonStyle.secondary,
                row=1,
            )
            btn.callback = self.make_toggle_action(action)
            self.add_item(btn)
            self.action_buttons[action] = btn

        # Mod log select (on row 2)
        self.channel_select = discord.ui.ChannelSelect(
            placeholder="Set mod log channel…",
            channel_types=[discord.ChannelType.text],
            row=2,
        )
        self.channel_select.callback = self.set_modlog
        self.add_item(self.channel_select)

        # Clear mod log button (on row 3, separate from channel select)
        self.clear_button = discord.ui.Button(
            label="Clear Mod Log",
            style=discord.ButtonStyle.danger,
            emoji="🗑️",
            row=3,
        )
        self.clear_button.callback = self.clear_modlog
        self.add_item(self.clear_button)

    # ─── Callbacks ─────────────────────────────
    async def toggle_ai(self, interaction: discord.Interaction):
        self.settings.ai_enabled = not self.settings.ai_enabled
        await guild_settings_manager.update(self.guild_id, ai_enabled=self.settings.ai_enabled)
        self.ai_button.label = "Disable AI" if self.settings.ai_enabled else "Enable AI"
        self.ai_button.style = discord.ButtonStyle.danger if self.settings.ai_enabled else discord.ButtonStyle.success
        embed = build_full_settings_embed(self.settings)
        await interaction.response.edit_message(embed=embed, view=self)


    def make_toggle_action(self, action: ActionType):
        async def callback(interaction: discord.Interaction):
            field = ACTION_FLAG_FIELDS[action]
            current = getattr(self.settings, field, True)
            new_val = not current
            setattr(self.settings, field, new_val)
            await guild_settings_manager.set_action_allowed(self.guild_id, action, new_val)
            # update button label & style
            btn = self.action_buttons[action]
            btn.label = f"{ACTION_UI_EMOJIS[action]} {ACTION_UI_LABELS[action]} {'✅' if new_val else '❌'}"
            btn.style = discord.ButtonStyle.success if new_val else discord.ButtonStyle.secondary
            embed = build_full_settings_embed(self.settings)
            await interaction.response.edit_message(embed=embed, view=self)
        return callback


    async def set_modlog(self, interaction: discord.Interaction):
        channel = self.channel_select.values[0]
        await guild_settings_manager.update(self.guild_id, mod_log_channel_id=ChannelID(channel.id))
        self.settings.mod_log_channel_id = ChannelID(channel.id)
        embed = build_full_settings_embed(self.settings)
        await interaction.response.edit_message(embed=embed, view=self)


    async def clear_modlog(self, interaction: discord.Interaction):
        await guild_settings_manager.update(self.guild_id, mod_log_channel_id=None)
        self.settings.mod_log_channel_id = None
        embed = build_full_settings_embed(self.settings)
        await interaction.response.edit_message(embed=embed, view=self)

# ──────────────────────────────────────────────
# Sending the embed + view
# ──────────────────────────────────────────────
async def send_full_settings(ctx: commands.Context, guild_id: GuildID):
    settings = await guild_settings_manager.get_settings(guild_id)
    embed = build_full_settings_embed(settings)
    view = FullSettingsView(guild_id, settings)
    await ctx.send(embed=embed, view=view)
