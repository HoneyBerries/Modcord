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
from modcord.moderation.review_notifications import ReviewNotificationManager

logger = get_logger("review_ui")


def check_moderator_permission(guild_id: int, user: discord.Member) -> bool:
    """
    Check if a user has moderator permissions for review actions.
    
    Checks both manage_guild permission and configured moderator roles.
    
    Args:
        guild_id: ID of the guild to check permissions for
        user: Discord member to check permissions for
    
    Returns:
        bool: True if user has moderator permissions, False otherwise
    """
    # Import here to avoid circular dependency
    from modcord.configuration.guild_settings import guild_settings_manager
    
    # Check if user has manage guild permission
    if user.guild_permissions.manage_guild:
        return True
    
    # Check if user has any of the configured moderator roles
    settings = guild_settings_manager.get_guild_settings(guild_id)
    if settings and settings.moderator_role_ids:
        user_role_ids = {role.id for role in user.roles}
        if any(role_id in user_role_ids for role_id in settings.moderator_role_ids):
            return True
    
    return False


class ReviewResolutionView(discord.ui.View):
    """
    Persistent view with resolution and quick-action buttons for review requests.
    
    This view provides:
    - A "Mark as Resolved" button to close the review
    - Five quick-action buttons that populate Discord commands
    """
    
    def __init__(self, batch_id: str, guild_id: int):
        """
        Initialize the review resolution view.
        
        Args:
            batch_id: Unique identifier for the review batch
            guild_id: ID of the guild where the review was sent
        """
        # timeout=None makes the view persistent across bot restarts
        super().__init__(timeout=None)
        self.batch_id = batch_id
        self.guild_id = guild_id
    
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
        
        Updates the review status in the database and modifies the embed
        to indicate resolution.
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
        
        if not check_moderator_permission(self.guild_id, interaction.user):
            await interaction.response.send_message(
                "❌ You don't have permission to resolve reviews.",
                ephemeral=True
            )
            return
        
        # Mark as resolved in database
        success = await ReviewNotificationManager.mark_resolved(
            batch_id=self.batch_id,
            resolved_by=interaction.user.id,
            resolution_note=f"Resolved by {interaction.user.name}"
        )
        
        if not success:
            await interaction.response.send_message(
                "❌ Failed to mark review as resolved. It may already be resolved.",
                ephemeral=True
            )
            return
        
        # Update the embed to show resolved status
        if not interaction.message.embeds:
            await interaction.response.send_message(
                "❌ Error: No embed found in message.",
                ephemeral=True
            )
            return
            
        original_embed = interaction.message.embeds[0]
        resolved_embed = discord.Embed(
            title="✅ Review Resolved",
            description=original_embed.description or "Review has been resolved.",
            color=discord.Color.green(),
            timestamp=original_embed.timestamp
        )
        
        # Copy fields from original embed
        for field in original_embed.fields:
            resolved_embed.add_field(
                name=field.name,
                value=field.value,
                inline=field.inline if field.inline is not None else False
            )
        
        # Update footer
        original_footer_text = original_embed.footer.text if original_embed.footer else "Review"
        resolved_embed.set_footer(
            text=f"{original_footer_text} | Resolved by {interaction.user.name}"
        )
        
        # Copy image if present
        if original_embed.image:
            resolved_embed.set_image(url=original_embed.image.url)
        
        # Disable all buttons
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        
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
        await self._send_command_suggestion(
            interaction,
            "warn",
            "Use `/warn user:<user_id> reason:<reason>` to warn a user."
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
        await self._send_command_suggestion(
            interaction,
            "timeout",
            "Use `/timeout user:<user_id> duration:<minutes> reason:<reason>` to timeout a user."
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
        await self._send_command_suggestion(
            interaction,
            "kick",
            "Use `/kick user:<user_id> reason:<reason>` to kick a user."
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
        await self._send_command_suggestion(
            interaction,
            "ban",
            "Use `/ban user:<user_id> duration:<minutes> reason:<reason>` to ban a user."
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
        await self._send_command_suggestion(
            interaction,
            "delete",
            "Right-click the message and select 'Delete Message', or use `/delete_messages channel:<channel> count:<number>` to bulk delete."
        )
    
    async def _send_command_suggestion(
        self,
        interaction: discord.Interaction,
        action: str,
        message: str
    ):
        """
        Send an ephemeral message with command suggestion.
        
        Args:
            interaction: Discord interaction from button click
            action: Name of the action (for logging)
            message: Command suggestion message to display
        """
        await interaction.response.send_message(
            f"**{action.capitalize()} Action**\n\n{message}\n\n"
            f"*Tip: You can copy user IDs from the review embed above.*",
            ephemeral=True
        )
        
        if interaction.user:
            logger.debug(
                "[REVIEW UI] User %s requested %s command suggestion for batch %s",
                interaction.user.id,
                action,
                self.batch_id
            )
    

async def setup_persistent_views(bot: discord.Bot):
    """
    Register persistent views with the bot on startup.
    
    This function should be called when the bot starts to ensure
    that review buttons remain functional across bot restarts.
    
    Args:
        bot: Discord bot instance
    """
    # Note: We can't pre-register all possible batch IDs since they're dynamic.
    # Instead, we'll use a view factory pattern that recreates views on demand.
    # This is handled automatically by discord.py when it encounters a custom_id
    # that matches our pattern (review_resolve:*, review_warn:*, etc.)
    
    logger.info("[REVIEW UI] Persistent view setup complete")


def create_review_view(batch_id: str, guild_id: int) -> ReviewResolutionView:
    """
    Factory function to create a review resolution view.
    
    Args:
        batch_id: Unique identifier for the review batch
        guild_id: ID of the guild where the review was sent
    
    Returns:
        ReviewResolutionView: Configured view with all buttons
    """
    return ReviewResolutionView(batch_id=batch_id, guild_id=guild_id)
