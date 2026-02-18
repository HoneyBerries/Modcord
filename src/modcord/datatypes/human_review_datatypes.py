from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple, Optional, Any

from modcord.datatypes.action_datatypes import ActionData
from modcord.datatypes.moderation_datatypes import ModerationUser, ModerationMessage


@dataclass(frozen=True, slots=True)
class HumanReviewData:
    """
    Immutable data structure representing a flagged user review for moderators.

    Attributes:
        action: The moderation action that triggered this review.
        user: Full user information encapsulated in a ModerationUser object.
        past_actions: A tuple of past ActionData objects for historical context.
        context_messages: Optional tuple of message IDs or content providing additional context.
        metadata: Optional dictionary for extra flags or UI hints (future-proofing).
    """

    action: ActionData
    user: ModerationUser
    past_actions: Tuple[ActionData, ...] = field(default_factory=tuple)
    context_messages: Optional[Tuple[ModerationMessage, ...]] = None
    metadata: Optional[dict[str, Any]] = field(default=None, hash=False, compare=False)

    # -------------------------
    # Helper / convenience methods
    # -------------------------

    def with_added_past_action(self, past_action: ActionData) -> HumanReviewData:
        """Return a new HumanReviewData with an additional past action appended."""
        return HumanReviewData(
            action=self.action,
            user=self.user,
            past_actions=self.past_actions + (past_action,),
            context_messages=self.context_messages,
            metadata=self.metadata,
        )

    def with_context_messages(self, *messages: ModerationMessage) -> HumanReviewData:
        """Return a new HumanReviewData with context messages added."""
        return HumanReviewData(
            action=self.action,
            user=self.user,
            past_actions=self.past_actions,
            context_messages=messages,
            metadata=self.metadata,
        )

    def with_metadata(self, **metadata_updates: Any) -> HumanReviewData:
        """Return a new HumanReviewData with metadata updated or added."""
        new_metadata = {**(self.metadata or {}), **metadata_updates}
        return HumanReviewData(
            action=self.action,
            user=self.user,
            past_actions=self.past_actions,
            context_messages=self.context_messages,
            metadata=new_metadata,
        )