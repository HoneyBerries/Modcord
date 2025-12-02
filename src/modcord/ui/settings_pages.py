"""
Paginated setup and settings UI using pycord.ext.pages.

This module provides:
- SetupPaginator: Initial bot setup flow (AI toggles + rules channel selection)
- SettingsPaginator: Full settings management (AI toggles + rules channel + review config)

Each page uses discord.ui.View components for interactive configuration.
"""

from __future__ import annotations

from typing import Optional, Sequence

import discord
from discord import ComponentType, Interaction
from discord.ui import Select
from discord.ext.pages import Paginator, Page

from modcord.settings.guild_settings_manager import guild_settings_manager
from modcord.datatypes.action_datatypes import ActionType
from modcord.datatypes.discord_datatypes import GuildID, ChannelID
from modcord.util.discord import discord_utils
from modcord.util.logger import get_logger

logger = get_logger("settings_pages")

# ============================================================================
# Constants
# ============================================================================

ACTION_UI_ORDER: tuple[ActionType, ...] = (
    ActionType.WARN,
    ActionType.DELETE,
    ActionType.TIMEOUT,
    ActionType.KICK,
    ActionType.BAN,
    ActionType.REVIEW,
)

ACTION_UI_LABELS: dict[ActionType, str] = {
    ActionType.WARN: "Warn",
    ActionType.DELETE: "Delete",
    ActionType.TIMEOUT: "Timeout",
    ActionType.KICK: "Kick",
    ActionType.BAN: "Ban",
    ActionType.REVIEW: "Review",
}

ACTION_UI_EMOJIS: dict[ActionType, str] = {
    ActionType.WARN: "⚠️",
    ActionType.DELETE: "🗑️",
    ActionType.TIMEOUT: "⏲️",
    ActionType.KICK: "👢",
    ActionType.BAN: "🔨",
    ActionType.REVIEW: "🛡️",
}

# ============================================================================
# Embed Builders
# ============================================================================

def build_moderation_settings_embed(guild_id: GuildID) -> discord.Embed:
    """Build embed for Page 1: AI moderation and action toggles."""
    settings = guild_settings_manager.get(guild_id)
    ai_status = "✅ Enabled" if settings.ai_enabled else "❌ Disabled"

    auto_actions_lines: list[str] = []
    for action in ACTION_UI_ORDER:
        enabled = guild_settings_manager.is_action_allowed(guild_id, action)
        emoji = ACTION_UI_EMOJIS.get(action, "⚙️")
        label = ACTION_UI_LABELS.get(action, action.value.title())
        state = "✅ ON" if enabled else "❌ OFF"
        auto_actions_lines.append(f"{emoji} **{label}**: {state}")

    embed = discord.Embed(
        title="🛠️ Moderation Settings",
        description=(
            "Configure AI moderation and automatic actions.\n"
            "Use the buttons below to toggle settings."
        ),
        color=discord.Color.blurple(),
    )
    embed.add_field(name="🤖 AI Moderation", value=ai_status, inline=False)
    embed.add_field(
        name="⚡ Automatic Actions",
        value="\n".join(auto_actions_lines),
        inline=False,
    )
    embed.set_footer(text="Page 1 • Moderation Settings")
    return embed


def build_rules_channel_embed(guild_id: GuildID) -> discord.Embed:
    """Build embed for Page 2: Rules channel selection."""
    settings = guild_settings_manager.get(guild_id)

    if settings.rules_channel_id:
        channel_mention = f"<#{settings.rules_channel_id.to_int()}>"
    else:
        channel_mention = "Not set"

    embed = discord.Embed(
        title="📜 Rules Channel",
        description=(
            "Select the channel containing your server rules.\n"
            "The bot will read and cache the rules from this channel for AI moderation."
        ),
        color=discord.Color.gold(),
    )
    embed.add_field(name="Current Rules Channel", value=channel_mention, inline=False)
    embed.set_footer(text="Page 2 • Rules Channel")
    return embed


def build_review_settings_embed(guild_id: GuildID) -> discord.Embed:
    """Build embed for Page 3: Review channels and moderator roles."""
    settings = guild_settings_manager.get(guild_id)

    channels = [f"<#{cid.to_int()}>" for cid in settings.review_channel_ids]
    roles = [f"<@&{rid}>" for rid in settings.moderator_role_ids]

    embed = discord.Embed(
        title="👮 Review Settings",
        description=(
            "Configure where AI review alerts are sent and which roles receive them.\n"
            "Use the selects below to add or remove channels and roles."
        ),
        color=discord.Color.green(),
    )
    embed.add_field(
        name="📢 Review Channels",
        value=", ".join(channels) if channels else "None configured",
        inline=False,
    )
    embed.add_field(
        name="🎭 Moderator Roles",
        value=", ".join(roles) if roles else "None configured",
        inline=False,
    )
    embed.set_footer(text="Page 3 • Review Settings")
    return embed


class SettingsPageView(discord.ui.View):
    """Base view for paginator pages that need access to the paginator instance."""

    def __init__(self, guild_id: GuildID, invoker_id: int):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.invoker_id = invoker_id
        self._paginator: Optional[Paginator] = None

    def bind_paginator(self, paginator: Paginator) -> None:
        self._paginator = paginator

    def _get_paginator(self) -> Paginator:
        if self._paginator is None:
            raise RuntimeError("Paginator has not been bound to this view")
        return self._paginator

    async def _edit_with_paginator(self, interaction: Interaction, embed: discord.Embed) -> None:
        paginator = self._get_paginator()
        await interaction.response.edit_message(embed=embed, view=paginator)


class ModerationSettingsView(SettingsPageView):
    """Interactive view for toggling AI moderation and action settings."""

    def __init__(self, guild_id: GuildID, invoker_id: int):
        super().__init__(guild_id, invoker_id)
        self._button_refs: dict[str, discord.ui.Button] = {}
        self._build_buttons()

    def _build_buttons(self) -> None:
        """Add buttons once; their state will be updated in-place."""
        settings = guild_settings_manager.get(self.guild_id)

        ai_enabled = settings.ai_enabled
        ai_btn = discord.ui.Button(
            label=f"🤖 AI Moderation: {'ON' if ai_enabled else 'OFF'}",
            style=discord.ButtonStyle.success if ai_enabled else discord.ButtonStyle.secondary,
            custom_id="toggle_ai",
            row=0,
        )
        ai_btn.callback = self._toggle_ai_callback
        self.add_item(ai_btn)
        self._button_refs["toggle_ai"] = ai_btn

        for idx, action in enumerate(ACTION_UI_ORDER):
            enabled = guild_settings_manager.is_action_allowed(self.guild_id, action)
            emoji = ACTION_UI_EMOJIS.get(action, "⚙️")
            label = ACTION_UI_LABELS.get(action, action.value.title())
            row = (idx // 3) + 1

            btn = discord.ui.Button(
                label=f"{emoji} {label}: {'ON' if enabled else 'OFF'}",
                style=discord.ButtonStyle.primary if enabled else discord.ButtonStyle.secondary,
                custom_id=f"toggle_action_{action.value}",
                row=row,
            )
            btn.callback = self._make_action_callback(action)
            self.add_item(btn)
            self._button_refs[f"toggle_action_{action.value}"] = btn

    def _update_button_states(self) -> None:
        """Update button labels and styles based on current settings."""
        settings = guild_settings_manager.get(self.guild_id)

        ai_btn = self._button_refs.get("toggle_ai")
        if ai_btn:
            ai_enabled = settings.ai_enabled
            ai_btn.label = f"🤖 AI Moderation: {'ON' if ai_enabled else 'OFF'}"
            ai_btn.style = (
                discord.ButtonStyle.success if ai_enabled else discord.ButtonStyle.secondary
            )

        for action in ACTION_UI_ORDER:
            btn = self._button_refs.get(f"toggle_action_{action.value}")
            if btn:
                enabled = guild_settings_manager.is_action_allowed(self.guild_id, action)
                emoji = ACTION_UI_EMOJIS.get(action, "⚙️")
                label = ACTION_UI_LABELS.get(action, action.value.title())
                btn.label = f"{emoji} {label}: {'ON' if enabled else 'OFF'}"
                btn.style = (
                    discord.ButtonStyle.primary if enabled else discord.ButtonStyle.secondary
                )

    async def _toggle_ai_callback(self, interaction: Interaction) -> None:
        if interaction.user is None or not discord_utils.has_elevated_permissions(interaction.user):
            await interaction.response.send_message(
                "You don't have permission to change these settings.", ephemeral=True
            )
            return

        settings = guild_settings_manager.get(self.guild_id)
        new_state = not settings.ai_enabled
        guild_settings_manager.update(self.guild_id, ai_enabled=new_state)
        self._update_button_states()
        await self._edit_with_paginator(
            interaction, build_moderation_settings_embed(self.guild_id)
        )

    def _make_action_callback(self, action: ActionType):
        async def callback(interaction: Interaction) -> None:
            if not interaction.user or not discord_utils.has_elevated_permissions(interaction.user):
                await interaction.response.send_message(
                    "You don't have permission to change these settings.", ephemeral=True
                )
                return

            current = guild_settings_manager.is_action_allowed(self.guild_id, action)
            guild_settings_manager.set_action_allowed(self.guild_id, action, not current)
            self._update_button_states()
            await self._edit_with_paginator(
                interaction, build_moderation_settings_embed(self.guild_id)
            )

        return callback


# ============================================================================
# Page 2: Rules Channel View
# ============================================================================

class RulesChannelSelect(Select):
    """Channel select for picking the rules channel."""
    
    def __init__(self, guild_id: GuildID):
        self.guild_id = guild_id
        super().__init__(
            select_type=ComponentType.channel_select,
            placeholder="Select Rules Channel",
            channel_types=[discord.ChannelType.text],
            min_values=0,
            max_values=1,
            row=0,
        )

    async def callback(self, interaction: Interaction) -> None:
        if interaction.user is None or not discord_utils.has_elevated_permissions(interaction.user):
            await interaction.response.send_message(
                "You don't have permission to change these settings.", ephemeral=True
            )
            return

        if self.values:
            channel = self.values[0]
            channel_id = ChannelID.from_channel(channel) if type(channel) is discord.TextChannel else None
            guild_settings_manager.update(self.guild_id, rules_channel_id=channel_id)
            logger.info(
                "[SETUP PAGES] Rules channel set to %s for guild %s",
                channel.id if type(channel) is discord.TextChannel else None, self.guild_id.to_int()
            )
        
        view = self.view
        if not isinstance(view, SettingsPageView):
            return
        await view._edit_with_paginator(
            interaction, build_rules_channel_embed(self.guild_id)
        )


class RulesChannelView(SettingsPageView):
    """Interactive view for selecting the rules channel."""

    def __init__(self, guild_id: GuildID, invoker_id: int):
        super().__init__(guild_id, invoker_id)

        # Channel select for rules channel
        self.add_item(RulesChannelSelect(guild_id))

        # Clear button
        clear_btn = discord.ui.Button(
            label="🗑️ Clear Rules Channel",
            style=discord.ButtonStyle.danger,
            row=1,
        )
        clear_btn.callback = self._clear_callback
        self.add_item(clear_btn)

    async def _clear_callback(self, interaction: Interaction) -> None:
        if interaction.user is None or not discord_utils.has_elevated_permissions(interaction.user):
            await interaction.response.send_message(
                "You don't have permission to change these settings.", ephemeral=True
            )
            return

        guild_settings_manager.update(self.guild_id, rules_channel_id=None)
        await self._edit_with_paginator(
            interaction, build_rules_channel_embed(self.guild_id)
        )


# ============================================================================
# Page 3: Review Settings View
# ============================================================================

class ReviewChannelSelect(Select):
    """Channel select for picking review channels (multi-select)."""
    
    def __init__(self, guild_id: GuildID):
        self.guild_id = guild_id
        super().__init__(
            select_type=ComponentType.channel_select,
            placeholder="Select Review Channels",
            channel_types=[discord.ChannelType.text],
            min_values=1,
            max_values=25,
            row=0,
        )

    async def callback(self, interaction: Interaction) -> None:
        if interaction.user is None or not discord_utils.has_elevated_permissions(interaction.user):
            await interaction.response.send_message(
                "You don't have permission to change these settings.", ephemeral=True
            )
            return

        channel_ids = [
            ChannelID.from_channel(ch) 
            for ch in self.values 
            if isinstance(ch, discord.TextChannel)
        ]
        guild_settings_manager.update(self.guild_id, review_channel_ids=channel_ids)
        view = self.view
        if not isinstance(view, SettingsPageView):
            return
        await view._edit_with_paginator(
            interaction, build_review_settings_embed(self.guild_id)
        )


class ModeratorRoleSelect(Select):
    """Role select for picking moderator roles (multi-select)."""
    
    def __init__(self, guild_id: GuildID):
        self.guild_id = guild_id
        super().__init__(
            select_type=ComponentType.role_select,
            placeholder="Select Moderator Roles to be Notified for Review",
            min_values=1,
            max_values=25,
            row=1,
        )

    async def callback(self, interaction: Interaction) -> None:
        if interaction.user is None or not discord_utils.has_elevated_permissions(interaction.user):
            await interaction.response.send_message(
                "You don't have permission to change these settings.", ephemeral=True
            )
            return

        role_ids = [role.id for role in self.values if isinstance(role, discord.Role)]
        guild_settings_manager.update(self.guild_id, moderator_role_ids=role_ids)
        view = self.view
        if not isinstance(view, SettingsPageView):
            return
        await view._edit_with_paginator(
            interaction, build_review_settings_embed(self.guild_id)
        )


class ReviewSettingsView(SettingsPageView):
    """Interactive view for configuring review channels and moderator roles."""

    def __init__(self, guild_id: GuildID, invoker_id: int):
        super().__init__(guild_id, invoker_id)

        # Channel select for review channels (multi-select)
        self.add_item(ReviewChannelSelect(guild_id))

        # Role select for moderator roles (multi-select)
        self.add_item(ModeratorRoleSelect(guild_id))

        # Clear buttons
        clear_channels_btn = discord.ui.Button(
            label="🗑️ Clear Channels",
            style=discord.ButtonStyle.danger,
            row=2,
        )
        clear_channels_btn.callback = self._clear_channels_callback
        self.add_item(clear_channels_btn)

        clear_roles_btn = discord.ui.Button(
            label="🗑️ Clear Roles",
            style=discord.ButtonStyle.danger,
            row=2,
        )
        clear_roles_btn.callback = self._clear_roles_callback
        self.add_item(clear_roles_btn)

    async def _clear_channels_callback(self, interaction: Interaction) -> None:
        if interaction.user is None or not discord_utils.has_elevated_permissions(interaction.user):
            await interaction.response.send_message(
                "You don't have permission to change these settings.", ephemeral=True
            )
            return

        guild_settings_manager.update(self.guild_id, review_channel_ids=[])
        await self._edit_with_paginator(
            interaction, build_review_settings_embed(self.guild_id)
        )

    async def _clear_roles_callback(self, interaction: Interaction) -> None:
        if interaction.user is None or not discord_utils.has_elevated_permissions(interaction.user):
            await interaction.response.send_message(
                "You don't have permission to change these settings.", ephemeral=True
            )
            return

        guild_settings_manager.update(self.guild_id, moderator_role_ids=[])
        await self._edit_with_paginator(
            interaction, build_review_settings_embed(self.guild_id)
        )


def _bind_page_views(paginator: Paginator, pages: Sequence[Page]) -> None:
    """Ensure views can edit the paginator message when their state changes."""
    for page in pages:
        view = page.custom_view
        if isinstance(view, SettingsPageView):
            view.bind_paginator(paginator)


# ============================================================================
# Paginator Factory Functions
# ============================================================================

def create_setup_paginator(guild_id: GuildID, invoker_id: int) -> Paginator:
    """
    Create a Paginator for the /setup command.
    
    Pages:
    1. Moderation Settings (AI toggle + action toggles)
    2. Rules Channel Selection
    """
    pages = [
        Page(
            embeds=[build_moderation_settings_embed(guild_id)],
            custom_view=ModerationSettingsView(guild_id, invoker_id),
        ),
        Page(
            embeds=[build_rules_channel_embed(guild_id)],
            custom_view=RulesChannelView(guild_id, invoker_id),
        ),
    ]

    paginator = Paginator(
        pages=pages,
        show_disabled=True,
        show_indicator=True,
        use_default_buttons=True,
        default_button_row=4,
        timeout=300,
    )
    _bind_page_views(paginator, pages)
    return paginator


def create_settings_paginator(guild_id: GuildID, invoker_id: int) -> Paginator:
    """
    Create a Paginator for the /settings command.
    
    Pages:
    1. Moderation Settings (AI toggle + action toggles)
    2. Rules Channel Selection
    3. Review Settings (channels + roles)
    """
    pages = [
        Page(
            embeds=[build_moderation_settings_embed(guild_id)],
            custom_view=ModerationSettingsView(guild_id, invoker_id),
        ),
        Page(
            embeds=[build_rules_channel_embed(guild_id)],
            custom_view=RulesChannelView(guild_id, invoker_id),
        ),
        Page(
            embeds=[build_review_settings_embed(guild_id)],
            custom_view=ReviewSettingsView(guild_id, invoker_id),
        ),
    ]

    paginator = Paginator(
        pages=pages,
        show_disabled=True,
        show_indicator=True,
        use_default_buttons=True,
        default_button_row=4,  # Move nav buttons to row 4 so custom views can use rows 0-3
        timeout=300,
    )
    _bind_page_views(paginator, pages)
    return paginator
