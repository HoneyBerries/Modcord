import datetime

import discord

from modcord.settings.guild_settings_manager import guild_settings_manager
from modcord.datatypes.action_datatypes import ActionType
from modcord.datatypes.discord_datatypes import GuildID, UserID
from modcord.util.logger import get_logger

logger = get_logger("guild_settings_ui")

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


async def build_settings_embed(guild_id: GuildID) -> discord.Embed:
    """
    Create a Discord embed summarizing current guild moderation settings.
    
    Builds a formatted embed showing the AI moderation status and which automatic
    moderation actions are enabled for the specified guild.
    
    Args:
        guild_id (GuildID): The Discord guild ID to fetch settings for.
    
    Returns:
        discord.Embed: A formatted embed with current settings information.
    """
    settings = await guild_settings_manager.get_settings(guild_id)
    ai_status = "Enabled ✅" if settings.ai_enabled else "Disabled ❌"

    auto_actions_lines: list[str] = []
    for action in ACTION_UI_ORDER:
        enabled = await guild_settings_manager.is_action_allowed(guild_id, action)
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
    """
    Interactive Discord UI view for managing guild-specific moderation settings.
    
    Provides button-based controls for toggling AI moderation and individual
    automatic action types (warn, delete, timeout, kick, ban). Only users with
    the Manage Server permission can interact with the controls.
    
    Attributes:
        guild_id (GuildID): The Discord guild ID this view manages settings for.
        invoker_id (UserID | None): The user ID who invoked the settings panel.
        timeout_seconds (int): How long the view remains active before timing out.
    
    Methods:
        refresh_items: Rebuild button set based on current settings.
        can_manage: Check if a member has permission to change settings.
        refresh_message: Update the settings embed and buttons.
        on_timeout: Disable all buttons when the view times out.
    """

    def __init__(self, guild_id: GuildID, invoker_id: UserID, timeout_seconds: int = 300):
        super().__init__(timeout=timeout_seconds)
        if not isinstance(guild_id, GuildID):
            guild_id = GuildID(guild_id)
        self.guild_id = guild_id
        self.invoker_id = invoker_id
        self._message: discord.Message | None = None
        # self.refresh_items() is now async and must be called externally

    @property
    def message(self) -> discord.Message | None:
        return self._message

    @message.setter
    def message(self, value: discord.Message | None) -> None:
        self._message = value

    async def refresh_items(self) -> None:
        """
        Rebuild the button set based on current guild settings.
        
        Clears all existing items and recreates buttons with current state,
        including the AI toggle button, individual action buttons, and close button.
        """

        self.clear_items()

        settings = await guild_settings_manager.get_settings(self.guild_id)
        ai_enabled = settings.ai_enabled
        self.add_item(ToggleAIButton(ai_enabled))

        for index, action in enumerate(ACTION_UI_ORDER, start=1):
            enabled = await guild_settings_manager.is_action_allowed(self.guild_id, action)
            label = ACTION_UI_LABELS.get(action, action.value.title())
            emoji = ACTION_UI_EMOJIS.get(action, "⚙️")
            row = ((index - 1) // 3) + 1
            self.add_item(ToggleActionButton(action, label, emoji, enabled, row=row))

        self.add_item(ClosePanelButton())

    def can_manage(self, member: discord.abc.Snowflake | None) -> bool:
        """
        Check if the interacting user has permission to manage guild settings.
        
        Requires the Manage Server (manage_guild) permission.
        
        Args:
            member (discord.abc.Snowflake | None): The member to check permissions for.
        
        Returns:
            bool: True if the member has Manage Server permission, False otherwise.
        """

        if member is None:
            return False

        permissions = getattr(member, "guild_permissions", None)
        return bool(getattr(permissions, "manage_guild", False))

    async def refresh_message(self, interaction: discord.Interaction, *, flash: str | None = None) -> None:
        """
        Refresh the settings embed and button states on the active message.
        
        Updates both the embed content and the interactive buttons to reflect
        the current settings state. Optionally displays a temporary flash message.
        
        Args:
            interaction (discord.Interaction): The interaction that triggered the refresh.
            flash (str | None): Optional temporary message to display above the embed.
        """

        await self.refresh_items()
        embed = await build_settings_embed(self.guild_id)

        try:
            # For ephemeral messages, we must use edit_original_response
            await interaction.response.edit_message(
                content=flash,
                embed=embed,
                view=self
            )
        except discord.InteractionResponded:
            # If already responded, try to edit the original response
            try:
                await interaction.edit_original_response(
                    content=flash,
                    embed=embed,
                    view=self
                )
            except discord.HTTPException as e:
                # Log but don't crash if we can't update
                pass
        except discord.HTTPException as e:
            # Handle any other Discord API errors gracefully
            pass

    async def on_timeout(self) -> None:
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        if self._message is not None:
            try:
                await self._message.edit(view=self)
            except discord.HTTPException as e:
                logger.debug("[GUILD SETTINGS UI] Failed to edit message on timeout: %s", e)


class ToggleAIButton(discord.ui.Button):
    """
    Button control for toggling AI moderation on/off for a guild.
    
    Changes color and label based on current state:
    - Green "ON" when AI moderation is enabled
    - Gray "OFF" when AI moderation is disabled
    
    Args:
        enabled (bool): Current AI moderation state.
    """

    def __init__(self, enabled: bool):
        label = "AI Moderation: ON" if enabled else "AI Moderation: OFF"
        emoji = "🟢" if enabled else "🔴"
        style = discord.ButtonStyle.success if enabled else discord.ButtonStyle.gray
        super().__init__(label=f"{emoji} {label}", style=style, row=0)

    async def callback(self, interaction: discord.Interaction) -> None:  # pragma: no cover - requires Discord runtime
        view: GuildSettingsView = self.view  # type: ignore[assignment]

        if not view.can_manage(interaction.user):
            await interaction.response.send_message(
                "You need the Manage Server permission to change settings.",
                ephemeral=True,
            )
            return

        settings = await guild_settings_manager.get_settings(view.guild_id)
        current = settings.ai_enabled
        new_state = not current
        await guild_settings_manager.update(view.guild_id, ai_enabled=new_state)
        await view.refresh_message(
            interaction,
            flash=f"AI moderation is now {'enabled' if new_state else 'disabled'}.",
        )


class ToggleActionButton(discord.ui.Button):
    """
    Button control for toggling a specific automatic moderation action type.
    
    Each button controls whether the AI can automatically apply a specific
    action type (warn, delete, timeout, kick, or ban) for the guild.
    
    Args:
        action (ActionType): The moderation action this button controls.
        label (str): Display label for the action.
        emoji (str): Emoji to display on the button.
        enabled (bool): Current enabled state for this action.
        row (int): Button row position (0-4).
    """

    def __init__(self, action: ActionType, label: str, emoji: str, enabled: bool, *, row: int):
        self.action = action
        self.action_label = label
        self.display_emoji = emoji
        super().__init__(
            label=f"{emoji} {label}: {'ON' if enabled else 'OFF'}",
            style=discord.ButtonStyle.primary if enabled else discord.ButtonStyle.gray,
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

        current = await guild_settings_manager.is_action_allowed(view.guild_id, self.action)
        new_state = not current
        await guild_settings_manager.set_action_allowed(view.guild_id, self.action, new_state)
        await view.refresh_message(
            interaction,
            flash=f"{self.display_emoji} {self.action_label} actions are now {'enabled' if new_state else 'disabled'}.",
        )


class ClosePanelButton(discord.ui.Button):
    """
    Button to close the settings panel and disable all controls.
    
    When clicked, disables all buttons in the view and attempts to delete
    the settings message to clean up the interface.
    """

    def __init__(self):
        super().__init__(label="Close", style=discord.ButtonStyle.secondary, row=4, emoji="❌")

    async def callback(self, interaction: discord.Interaction) -> None:  # pragma: no cover - requires Discord runtime
        view: GuildSettingsView = self.view  # type: ignore[assignment]
        for child in view.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True

        # For ephemeral messages we must use interaction methods; for non-ephemeral
        # messages we can delete the message entirely to close the panel.
        try:
            if interaction.response.is_done():
                # If we've already responded, edit the original response first to
                # show the disabled controls, then attempt to delete the message.
                await interaction.edit_original_response(content="Settings panel closed.", view=view)
                # Try to delete the original response message
                try:
                    msg = await interaction.original_response()
                    await msg.delete()
                except Exception:
                    # If deletion fails (e.g., message already deleted), ignore.
                    pass
            else:
                # If no response yet, edit the ephemeral/response and then delete
                await interaction.response.edit_message(content="Settings panel closed.", view=view)
                # For ephemeral responses there is no message to delete; nothing else to do.
                # If the message was not ephemeral, interaction.response.edit_message
                # returns the message in some implementations; we try to delete via
                # interaction.original_response() to be safe.
                try:
                    msg = await interaction.original_response()
                    await msg.delete()
                except Exception:
                    pass
        except discord.HTTPException:
            # If editing the response fails, fall back to deleting the stored message
            target = interaction.message or view.message
            if target is not None:
                try:
                    await target.delete()
                except Exception:
                    pass
