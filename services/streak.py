"""Streak tracking system for BOWA.

Tracks user consistency streaks based on session completions.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from services.memory import load_user_memory, save_user_memory

logger = logging.getLogger(__name__)


def get_user_streak(user_id: str) -> dict[str, Any]:
    """Return the user's current streak data."""
    memory = load_user_memory(user_id) or {}
    return {
        "current_streak": memory.get("current_streak", 0),
        "longest_streak": memory.get("longest_streak", 0),
        "last_active_date": memory.get("last_active_date"),
    }


def update_streak(user_id: str, completed: bool) -> dict[str, Any]:
    """Update streak based on session completion."""
    memory = load_user_memory(user_id) or {}
    today = datetime.now(timezone.utc).date().isoformat()
    last_active = memory.get("last_active_date")

    current_streak = memory.get("current_streak", 0)
    longest_streak = memory.get("longest_streak", 0)

    if completed:
        if last_active == today:
            # Already completed today, no change
            pass
        elif last_active and datetime.fromisoformat(last_active).date() == datetime.now(timezone.utc).date() - timedelta(days=1):
            # Consecutive day
            current_streak += 1
        else:
            # New streak or restart
            current_streak = 1
        longest_streak = max(longest_streak, current_streak)
        memory["last_active_date"] = today
    else:
        # Miss: reset streak
        current_streak = 0
        # Keep longest_streak

    memory["current_streak"] = current_streak
    memory["longest_streak"] = longest_streak
    save_user_memory(user_id, memory)

    logger.info("bowa_streak user=%s current=%d longest=%d", user_id, current_streak, longest_streak)
    return {
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "last_active_date": today if completed else last_active,
    }