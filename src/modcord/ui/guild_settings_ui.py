import datetime
from typing import Optional

import discord

from modcord.configuration.guild_settings import guild_settings_manager
from modcord.util.moderation_datatypes import ActionType


ACTION_UI_ORDER: tuple[ActionType, ...] = (
    ActionType.WARN,
    ActionType.DELETE,
    ActionType.TIMEOUT,
    ActionType.KICK,
    ActionType.BAN,
)

ACTION_UI_LABELS: dict[ActionType, str] = {
    ActionType.WARN: "Warn",
    ActionType.DELETE: "Delete",
    ActionType.TIMEOUT: "Timeout",
    ActionType.KICK: "Kick",
    ActionType.BAN: "Ban",
}

ACTION_UI_EMOJIS: dict[ActionType, str] = {
    ActionType.WARN: "⚠️",
    ActionType.DELETE: "🗑️",
    ActionType.TIMEOUT: "⏲️",
    ActionType.KICK: "👢",
    ActionType.BAN: "🔨",
}


def build_settings_embed(guild_id: int) -> discord.Embed:
    """Create an embed summarizing the current guild settings."""

    settings = guild_settings_manager.get_guild_settings(guild_id)
    ai_status = "Enabled ✅" if settings.ai_enabled else "Disabled ❌"

    auto_actions_lines: list[str] = []
    for action in ACTION_UI_ORDER:
        enabled = guild_settings_manager.is_action_allowed(guild_id, action)
        emoji = ACTION_UI_EMOJIS.get(action, "⚙️")
        label = ACTION_UI_LABELS.get(action, action.value.title())
        state = "ON" if enabled else "OFF"
        auto_actions_lines.append(f"{emoji} **{label}** — {state}")

    description = (
        "Use the controls below to configure Modcord's moderation behaviour. "
        "Changes take effect immediately for this server."
    )

    embed = discord.Embed(
        title="Modcord Settings",
        description=description,
        color=discord.Color.blurple(),
        timestamp=datetime.datetime.now(datetime.timezone.utc),
    )
    embed.add_field(name="AI Moderation", value=ai_status, inline=False)
    embed.add_field(
        name="Automatic Actions",
        value="\n".join(auto_actions_lines) or "No automatic actions configured.",
        inline=False,
    )
    embed.set_footer(text="Only members with Manage Server can change these settings.")
    return embed


class GuildSettingsView(discord.ui.View):
    """Interactive view that exposes guild settings via buttons."""

    def __init__(self, guild_id: int, invoker_id: int, *, timeout_seconds: int = 300):
        super().__init__(timeout=timeout_seconds)
        self.guild_id = guild_id
        self.invoker_id = invoker_id
        self._message: Optional[discord.Message] = None
        self.refresh_items()

    @property
    def message(self) -> Optional[discord.Message]:
        return self._message

    @message.setter
    def message(self, value: Optional[discord.Message]) -> None:
        self._message = value

    def refresh_items(self) -> None:
        """Rebuild button set based on current settings."""

        self.clear_items()

        ai_enabled = guild_settings_manager.is_ai_enabled(self.guild_id)
        self.add_item(ToggleAIButton(ai_enabled))

        for index, action in enumerate(ACTION_UI_ORDER, start=1):
            enabled = guild_settings_manager.is_action_allowed(self.guild_id, action)
            label = ACTION_UI_LABELS.get(action, action.value.title())
            emoji = ACTION_UI_EMOJIS.get(action, "⚙️")
            row = ((index - 1) // 3) + 1
            self.add_item(ToggleActionButton(action, label, emoji, enabled, row=row))

        self.add_item(ClosePanelButton())

    def can_manage(self, member: Optional[discord.abc.Snowflake]) -> bool:
        """Check whether the interacting user can manage guild settings."""

        if member is None:
            return False

        permissions = getattr(member, "guild_permissions", None)
        return bool(getattr(permissions, "manage_guild", False))

    async def refresh_message(self, interaction: discord.Interaction, *, flash: Optional[str] = None) -> None:
        """Refresh the embed + buttons on the active message."""

        self.refresh_items()
        embed = build_settings_embed(self.guild_id)

        content = flash

        if not interaction.response.is_done():
            await interaction.response.defer()

        message = interaction.message or self._message
        if message is not None:
            await message.edit(content=content, embed=embed, view=self)

    async def on_timeout(self) -> None:  # pragma: no cover - relies on Discord timers
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        if self._message is not None:
            try:
                await self._message.edit(view=self)
            except discord.HTTPException:
                pass


class ToggleAIButton(discord.ui.Button):
    """Button to toggle AI moderation enablement."""

    def __init__(self, enabled: bool):
        label = "AI Moderation: ON" if enabled else "AI Moderation: OFF"
        emoji = "🟢" if enabled else "🔴"
        style = discord.ButtonStyle.success if enabled else discord.ButtonStyle.danger
        super().__init__(label=f"{emoji} {label}", style=style, row=0)

    async def callback(self, interaction: discord.Interaction) -> None:  # pragma: no cover - requires Discord runtime
        view: GuildSettingsView = self.view  # type: ignore[assignment]

        if not view.can_manage(interaction.user):
            await interaction.response.send_message(
                "You need the Manage Server permission to change settings.",
                ephemeral=True,
            )
            return

        current = guild_settings_manager.is_ai_enabled(view.guild_id)
        new_state = not current
        guild_settings_manager.set_ai_enabled(view.guild_id, new_state)
        await view.refresh_message(
            interaction,
            flash=f"AI moderation is now {'enabled' if new_state else 'disabled'}.",
        )


class ToggleActionButton(discord.ui.Button):
    """Button that toggles a specific moderation action type."""

    def __init__(self, action: ActionType, label: str, emoji: str, enabled: bool, *, row: int):
        self.action = action
        self.action_label = label
        self.emoji = emoji
        super().__init__(
            label=f"{emoji} {label}: {'ON' if enabled else 'OFF'}",
            style=discord.ButtonStyle.primary if enabled else discord.ButtonStyle.secondary,
            row=row,
        )

    async def callback(self, interaction: discord.Interaction) -> None:  # pragma: no cover - requires Discord runtime
        view: GuildSettingsView = self.view  # type: ignore[assignment]

        if not view.can_manage(interaction.user):
            await interaction.response.send_message(
                "You need the Manage Server permission to change settings.",
                ephemeral=True,
            )
            return

        current = guild_settings_manager.is_action_allowed(view.guild_id, self.action)
        new_state = not current
        guild_settings_manager.set_action_allowed(view.guild_id, self.action, new_state)
        await view.refresh_message(
            interaction,
            flash=f"{self.emoji} {self.action_label} actions are now {'enabled' if new_state else 'disabled'}.",
        )


class ClosePanelButton(discord.ui.Button):
    """Button to close the settings panel and disable controls."""

    def __init__(self):
        super().__init__(label="Close", style=discord.ButtonStyle.secondary, row=4)

    async def callback(self, interaction: discord.Interaction) -> None:  # pragma: no cover - requires Discord runtime
        view: GuildSettingsView = self.view  # type: ignore[assignment]
        for child in view.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True

        if not interaction.response.is_done():
            await interaction.response.defer()

        target_message = interaction.message or view.message
        if target_message is not None:
            await target_message.edit(content="Settings panel closed.", view=view)
