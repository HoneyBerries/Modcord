"""
Guild settings embed UI — redesigned with select-menu navigation.

Each settings category renders its own focused embed + controls.
Adding new categories only requires a new SettingsCategory entry and
a corresponding build_*_embed / *View pair — the nav select grows
automatically.

Categories (extensible):
  • AI          — enable/disable AI moderation
  • Actions     — toggle per-action-type flags
  • Audit Log     — set / clear the mod log channel
"""

from __future__ import annotations

import datetime
from enum import Enum
from typing import Callable, Awaitable

import discord
from discord.ext import commands

from modcord.datatypes.action_datatypes import ActionType
from modcord.datatypes.discord_datatypes import GuildID, ChannelID
from modcord.datatypes.guild_settings import GuildSettings, ACTION_FLAG_FIELDS
from modcord.settings.guild_settings_manager import guild_settings_manager

# ──────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────

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
    ActionType.TIMEOUT: "⏱️",
    ActionType.KICK: "👢",
    ActionType.BAN: "🔨",
}


class SettingsCategory(str, Enum):
    AI = "ai"
    ACTIONS = "actions"
    AUDIT_LOG = "audit_log"

    # Add new categories here — they'll appear in the nav select automatically.


CATEGORY_META: dict[SettingsCategory, dict] = {
    SettingsCategory.AI: {
        "label": "AI Moderation",
        "emoji": "📊",
        "description": "Enable or disable AI-driven moderation",
    },
    SettingsCategory.ACTIONS: {
        "label": "Automatic Actions",
        "emoji": "⚙️",
        "description": "Toggle which actions the bot may take",
    },
    SettingsCategory.AUDIT_LOG: {
        "label": "Audit Log Channel",
        "emoji": "🗒️",
        "description": "Where moderation events are logged",
    },
}


# ──────────────────────────────────────────────────────────────
# Embed builders  (one per category)
# ──────────────────────────────────────────────────────────────

def _base_embed(title: str, description: str, color: discord.Color) -> discord.Embed:
    return discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.datetime.now(datetime.timezone.utc),
    )


def build_ai_embed(settings: GuildSettings) -> discord.Embed:
    status = "**Enabled**" if settings.ai_enabled else "**Disabled**"
    embed = _base_embed(
        title="AI Moderation Settings",
        description=(
            f"Current status: {status}\n\n"
            "When enabled, the bot uses an LLM to review messages "
            "and trigger moderation actions if necessary."
        ),
        color=discord.Color.blurple() if settings.ai_enabled else discord.Color.greyple(),
    )
    embed.set_footer(text="Use the button below to toggle AI moderation.")
    return embed


def build_actions_embed(settings: GuildSettings) -> discord.Embed:
    embed = _base_embed(
        title="Automatic Actions Settings",
        description="Toggle which moderation actions the bot is allowed to apply automatically.",
        color=discord.Color.og_blurple(),
    )
    for a in ACTION_UI_ORDER:
        enabled = getattr(settings, ACTION_FLAG_FIELDS[a], True)
        embed.add_field(
            name=f"{ACTION_UI_EMOJIS[a]}  {ACTION_UI_LABELS[a]}",
            value="Enabled ✅" if enabled else "Disabled ❌",
            inline=True,
        )

    embed.set_footer(text="Click an action button to toggle it.")
    return embed


def build_audit_log_embed(settings: GuildSettings) -> discord.Embed:
    channel_value = (
        f"<#{int(settings.audit_log_channel_id)}>"
        if settings.audit_log_channel_id
        else "*Not configured*"
    )
    embed = _base_embed(
        title="Audit Log Channel Settings",
        description="All automatic moderation events will be posted to this channel.",
        color=discord.Color.teal(),
    )
    embed.add_field(name="Current Channel", value=channel_value, inline=False)
    embed.set_footer(text="Use the channel select or Clear button to update.")

    return embed


# Map each category to its embed builder
EMBED_BUILDERS: dict[SettingsCategory, Callable[[GuildSettings], discord.Embed]] = {
    SettingsCategory.AI: build_ai_embed,
    SettingsCategory.ACTIONS: build_actions_embed,
    SettingsCategory.AUDIT_LOG: build_audit_log_embed,
}


# ──────────────────────────────────────────────────────────────
# Category-specific control views
# ──────────────────────────────────────────────────────────────

class AIControlView(discord.ui.View):
    """Controls shown when the AI category is active."""

    def __init__(self, parent: SettingsRootView):
        super().__init__(timeout=None)
        self.parent = parent
        s = parent.settings

        btn = discord.ui.Button(
            label="Disable AI" if s.ai_enabled else "Enable AI",
            style=discord.ButtonStyle.danger if s.ai_enabled else discord.ButtonStyle.success,
            emoji="📊",
            row=0,
        )
        btn.callback = self._toggle_ai
        self.add_item(btn)
        self._btn = btn

    async def _toggle_ai(self, interaction: discord.Interaction):
        s = self.parent.settings
        s.ai_enabled = not s.ai_enabled

        await guild_settings_manager.update(self.parent.guild_id, ai_enabled=s.ai_enabled)
        self._btn.label = "Disable AI" if s.ai_enabled else "Enable AI"
        self._btn.style = (
            discord.ButtonStyle.danger if s.ai_enabled else discord.ButtonStyle.success
        )

        await self.parent.refresh(interaction)


class ActionsControlView(discord.ui.View):
    """Controls shown when the Actions category is active."""

    def __init__(self, parent: SettingsRootView):
        super().__init__(timeout=None)
        self.parent = parent
        self._btns: dict[ActionType, discord.ui.Button] = {}

        for action in ACTION_UI_ORDER:
            enabled = getattr(parent.settings, ACTION_FLAG_FIELDS[action], True)
            btn = discord.ui.Button(
                label=f"{ACTION_UI_LABELS[action]}",
                style=discord.ButtonStyle.success if enabled else discord.ButtonStyle.red,
                emoji=ACTION_UI_EMOJIS[action],
                row=0,
            )

            btn.callback = self._make_toggle(action)
            self.add_item(btn)
            self._btns[action] = btn


    def _make_toggle(self, action: ActionType) -> Callable[[discord.Interaction], Awaitable[None]]:
        async def callback(interaction: discord.Interaction):
            s = self.parent.settings
            field = ACTION_FLAG_FIELDS[action]
            new_val = not getattr(s, field, True)
            setattr(s, field, new_val)
            await guild_settings_manager.set_action_allowed(self.parent.guild_id, action, new_val)
            btn = self._btns[action]
            btn.label = (
                f"{ACTION_UI_EMOJIS[action]} {ACTION_UI_LABELS[action]} {'✅' if new_val else '❌'}"
            )
            btn.style = discord.ButtonStyle.success if new_val else discord.ButtonStyle.secondary
            await self.parent.refresh(interaction)

        return callback




class AuditLogControlView(discord.ui.View):
    """Controls shown when the Mod Log category is active."""

    def __init__(self, parent: SettingsRootView):
        super().__init__(timeout=None)
        self.parent = parent

        channel_select = discord.ui.ChannelSelect(
            placeholder="Change audit log channel…",
            channel_types=[discord.ChannelType.text],
            row=0,
        )
        channel_select.callback = self._set_channel
        self.add_item(channel_select)

        clear_btn = discord.ui.Button(
            label="Remove Audit Log",
            style=discord.ButtonStyle.danger,
            emoji="🗑️",
            row=1,
        )
        clear_btn.callback = self._clear_channel
        self.add_item(clear_btn)

    async def _set_channel(self, interaction: discord.Interaction):
        channel = interaction.data["values"][0]  # ChannelSelect value
        channel_id = ChannelID(int(channel))
        await guild_settings_manager.update(
            self.parent.guild_id, audit_log_channel_id=channel_id
        )
        self.parent.settings.audit_log_channel_id = channel_id
        await self.parent.refresh(interaction)

    async def _clear_channel(self, interaction: discord.Interaction):
        await guild_settings_manager.update(
            self.parent.guild_id, audit_log_channel_id=None
        )
        self.parent.settings.audit_log_channel_id = None
        await self.parent.refresh(interaction)




CONTROL_VIEWS: dict[
    SettingsCategory,
    Callable[["SettingsRootView"], discord.ui.View],
] = {
    SettingsCategory.AI: AIControlView,
    SettingsCategory.ACTIONS: ActionsControlView,
    SettingsCategory.AUDIT_LOG: AuditLogControlView,
}


# ──────────────────────────────────────────────────────────────
# Root view  (nav select + active category controls)
# ──────────────────────────────────────────────────────────────

class SettingsRootView(discord.ui.View):
    """
    Composes the nav select menu with whichever category-specific
    control view is currently active.

    Layout:
      Row 0  — category navigation select menu
      Row 1+ — controls for the active category (injected dynamically)
    """

    def __init__(self, guild_id: GuildID, settings: GuildSettings):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.settings = settings
        self.active_category = SettingsCategory.AI

        # Nav select (row 0)
        self._nav = discord.ui.Select(
            placeholder="📂  Select a settings category…",
            options=[
                discord.SelectOption(
                    label=meta["label"],
                    value=cat.value,
                    emoji=meta["emoji"],
                    description=meta["description"],
                )
                for cat, meta in CATEGORY_META.items()
            ],
            row=0,
        )
        self._nav.callback = self._on_nav
        self.add_item(self._nav)

        # Inject initial control view items
        self._inject_controls()

    def _inject_controls(self) -> None:
        """Add control items for the active category (rows 1+)."""
        control_view = CONTROL_VIEWS[self.active_category](self)
        for item in control_view.children:
            # Shift rows down by 1 so they sit below the nav select
            if item.row is not None:
                item.row += 1
            else:
                item.row = 1
            self.add_item(item)

    def _remove_controls(self) -> None:
        """Remove all items except the nav select (row 0)."""
        to_remove = [item for item in self.children if item is not self._nav]
        for item in to_remove:
            self.remove_item(item)

    async def _on_nav(self, interaction: discord.Interaction) -> None:
        selected = SettingsCategory(self._nav.values[0])
        self.active_category = selected
        self._remove_controls()
        self._inject_controls()
        await self.refresh(interaction)

    async def refresh(self, interaction: discord.Interaction) -> None:
        """Re-render the embed for the active category."""
        embed = EMBED_BUILDERS[self.active_category](self.settings)
        await interaction.response.edit_message(embed=embed, view=self)


# ──────────────────────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────────────────────

async def send_full_settings(ctx: commands.Context, guild_id: GuildID) -> None:
    """Send the settings UI to a command context."""
    settings = await guild_settings_manager.get_settings(guild_id)
    embed = build_ai_embed(settings)   # default to first category
    view = SettingsRootView(guild_id, settings)
    await ctx.send(embed=embed, view=view)
