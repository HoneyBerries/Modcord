"""
Interactive UI components for human moderator review system.

This module provides Discord UI views and buttons for moderators to interact
with review requests. It includes resolution buttons and quick-action buttons
that populate Discord commands for moderators to execute.

Key Features:
- Mark as Resolved: Updates review status and modifies embed
- Quick action buttons: Pre-populate Discord commands for common actions
- Persistent views: Buttons remain functional across bot restarts
"""

from __future__ import annotations
import discord
from modcord.util.logger import get_logger
from modcord.util.discord_utils import has_review_permission
from modcord.util.review_embeds import build_resolved_review_embed
from modcord.moderation.moderation_datatypes import ActionType

logger = get_logger("review_ui")

QUICK_ACTION_MESSAGES: dict[ActionType, str] = {
    ActionType.WARN: "Use `/warn user:<user> reason:<reason>` to warn this user.",
    ActionType.TIMEOUT: "Use `/timeout user:<user> duration:<duration> reason:<reason>` to timeout this user.",
    ActionType.KICK: "Use `/kick user:<user> reason:<reason>` to kick this user.",
    ActionType.BAN: "Use `/ban user:<user> duration:<duration> reason:<reason>` to ban this user.",
    ActionType.DELETE: "⚠️ Delete command is not yet implemented. Please delete the message manually from the channel.",
}


class HumanReviewResolutionView(discord.ui.View):
    """
    Persistent view with resolution and quick-action buttons for review requests.
    
    This view provides:
    - A "Mark as Resolved" button to close the review
    - Five quick-action buttons that populate Discord commands
    """
    
    def __init__(self, batch_id: str, guild_id: int, bot: discord.Bot | None = None):
        """
        Initialize the review resolution view.
        
        Args:
            batch_id: Unique identifier for the review batch
            guild_id: ID of the guild where the review was sent
            bot: Optional bot instance for cross-channel synchronization
        """
        # timeout=None makes the view persistent across bot restarts
        super().__init__(timeout=None)
        self.batch_id = batch_id
        self.guild_id = guild_id
        self.bot = bot
    
    @discord.ui.button(
        label="✅ Mark as Resolved",
        style=discord.ButtonStyle.success,
        row=0
    )
    async def resolve_button(
        self,
        button: discord.ui.Button,
        interaction: discord.Interaction
    ):
        """
        Handle the "Mark as Resolved" button click.
        
        Modifies the embed to indicate resolution.
        """
        # Null checks
        if interaction.user is None or interaction.message is None:
            await interaction.response.send_message(
                "❌ Error: Unable to process this interaction.",
                ephemeral=True
            )
            return
        
        # Check if user has permission (has any moderator role or manage guild)
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "❌ You don't have permission to resolve reviews.",
                ephemeral=True
            )
            return
        
        if not has_review_permission(self.guild_id, interaction.user):
            await interaction.response.send_message(
                "❌ You don't have permission to resolve reviews.",
                ephemeral=True
            )
            return
        
        # Update the current embed to show resolved status using utility function
        if not interaction.message.embeds:
            await interaction.response.send_message(
                "❌ Error: No embed found in message.",
                ephemeral=True
            )
            return
            
        original_embed = interaction.message.embeds[0]
        resolved_embed = build_resolved_review_embed(original_embed, interaction.user.name)
        
        # Disable all buttons
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        
        # Update the current message first
        await interaction.response.edit_message(embed=resolved_embed, view=self)
        
        if interaction.user:
            logger.info(
                "[REVIEW UI] Review batch %s resolved by user %s in guild %s",
                self.batch_id,
                interaction.user.id,
                self.guild_id
            )
    
    @discord.ui.button(
        label="⚠️ Warn",
        style=discord.ButtonStyle.secondary,
        row=1
    )
    async def warn_button(
        self,
        button: discord.ui.Button,
        interaction: discord.Interaction
    ):
        """Pre-populate a /warn command for the moderator."""
        await self.send_command_suggestion(
            interaction,
            ActionType.WARN,
        )
    
    @discord.ui.button(
        label="⏱️ Timeout",
        style=discord.ButtonStyle.secondary,
        row=1
    )
    async def timeout_button(
        self,
        button: discord.ui.Button,
        interaction: discord.Interaction
    ):
        """Pre-populate a /timeout command for the moderator."""
        await self.send_command_suggestion(
            interaction,
            ActionType.TIMEOUT,
        )
    
    @discord.ui.button(
        label="🚪 Kick",
        style=discord.ButtonStyle.secondary,
        row=1
    )
    async def kick_button(
        self,
        button: discord.ui.Button,
        interaction: discord.Interaction
    ):
        """Pre-populate a /kick command for the moderator."""
        await self.send_command_suggestion(
            interaction,
            ActionType.KICK,
        )
    
    @discord.ui.button(
        label="🔨 Ban",
        style=discord.ButtonStyle.secondary,
        row=2
    )
    async def ban_button(
        self,
        button: discord.ui.Button,
        interaction: discord.Interaction
    ):
        """Pre-populate a /ban command for the moderator."""
        await self.send_command_suggestion(
            interaction,
            ActionType.BAN,
        )
    
    @discord.ui.button(
        label="🗑️ Delete",
        style=discord.ButtonStyle.secondary,
        row=2
    )
    async def delete_button(
        self,
        button: discord.ui.Button,
        interaction: discord.Interaction
    ):
        """Suggest message deletion to the moderator."""
        await self.send_command_suggestion(
            interaction,
            ActionType.DELETE,
        )
    
    async def send_command_suggestion(
        self,
        interaction: discord.Interaction,
        action_type: ActionType,
    ):
        """
        Send an ephemeral message with command suggestion.
        
        Args:
            interaction: Discord interaction from button click
            action: Name of the action (for logging)
            message: Command suggestion message to display
        """
        message = QUICK_ACTION_MESSAGES.get(action_type)
        if not message:
            logger.warning("[REVIEW UI] No quick-action template configured for %s", action_type.value)
            message = "Refer to the server's moderation commands for the correct syntax."

        await interaction.response.send_message(
            f"**{action_type.value.capitalize()} Action**\n\n{message}\n\n"
            f"*Tip: You can copy user IDs from the review embed above.*",
            ephemeral=True
        )
        
        if interaction.user:
            logger.debug(
                "[REVIEW UI] User %s requested %s command suggestion for batch %s",
                interaction.user.id,
                action_type.value,
                self.batch_id
            )


def create_review_view(batch_id: str, guild_id: int, bot: discord.Bot | None = None) -> HumanReviewResolutionView:
    """
    Factory function to create a review resolution view.
    
    Args:
        batch_id: Unique identifier for the review batch
        guild_id: ID of the guild where the review was sent
        bot: Optional bot instance for cross-channel synchronization
    
    Returns:
        HumanReviewResolutionView: Configured view with all buttons
    """
    return HumanReviewResolutionView(batch_id=batch_id, guild_id=guild_id, bot=bot)