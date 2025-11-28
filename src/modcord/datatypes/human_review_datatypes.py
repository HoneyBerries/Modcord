"""
Human review data structures for moderator evaluation.

This module defines data structures used for presenting flagged users
to human moderators for review.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from modcord.datatypes.action_datatypes import ActionData
from modcord.datatypes.moderation_datatypes import ModerationUser


@dataclass
class HumanReviewData:
    """
    Represents a user-centric review item for human moderator evaluation.

    Encapsulates all relevant context for a user flagged for review, including:
    - The triggering moderation action and reason
    - Complete user information and a list of past moderation actions

    Used to present a holistic view of the user's behavior, enabling moderators to assess patterns and make informed decisions.
    """

    action: ActionData
    user: ModerationUser
    past_actions: List[ActionData] = field(default_factory=list)