"""Reward engine for BOWA.

Generates rewards based on user state and session results.
"""

import logging
from typing import Any

from services.streak import get_user_streak

logger = logging.getLogger(__name__)


def generate_reward(user_state: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Generate a reward based on user state and session result."""
    user_id = user_state.get("user_id", "unknown")
    completed = result.get("completed", False)
    streak = get_user_streak(user_id)
    current_streak = streak["current_streak"]
    longest_streak = streak["longest_streak"]

    if not completed:
        # Failure reward
        reward_type = "failure"
        message = "You broke the streak. Restart today—don't let it slide."
        impact = "streak_reset"
    elif current_streak == 1 and longest_streak == 1:
        # First completion
        reward_type = "small"
        message = "Good start. That's 1 in a row."
        impact = "first_completion"
    elif current_streak in [3, 7, 14]:
        # Milestone
        reward_type = "milestone"
        message = f"Good. That's {current_streak} in a row. Keep it going."
        impact = f"streak_{current_streak}"
    elif current_streak > longest_streak - 1 and longest_streak > 1:
        # Comeback
        reward_type = "recovery"
        message = "You're back. That matters more than perfection."
        impact = "comeback"
    else:
        # Regular success
        reward_type = "small"
        message = f"Good. That's {current_streak} in a row. Keep it going."
        impact = "continued_streak"

    logger.info("bowa_reward user=%s type=%s impact=%s", user_id, reward_type, impact)
    return {
        "reward_type": reward_type,
        "message": message,
        "impact": impact,
    }