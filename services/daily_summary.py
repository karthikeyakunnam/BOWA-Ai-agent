"""Daily summary generator for BOWA.

Creates end-of-day summaries of user progress.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from services.memory import load_user_memory, save_user_memory
from services.streak import get_user_streak

logger = logging.getLogger(__name__)


def generate_daily_summary(user_id: str) -> dict[str, Any]:
    """Generate a daily summary for the user."""
    memory = load_user_memory(user_id) or {}
    streak = get_user_streak(user_id)
    current_streak = streak["current_streak"]

    # For simplicity, assume we track daily completions in memory
    # In a real system, this would be more sophisticated
    today_sessions = memory.get("today_sessions_completed", 0)
    today_missed = memory.get("today_sessions_missed", 0)

    if today_sessions > 0:
        message = f"Today: Completed {today_sessions}, Missed {today_missed}. Streak: {current_streak} days."
        if current_streak > 1:
            message += " You're improving. Stay consistent tomorrow."
        else:
            message += " Good start. Build on this."
    else:
        message = f"Today: No sessions completed. Streak: {current_streak} days. Start fresh tomorrow."

    # Reset daily counters
    memory["today_sessions_completed"] = 0
    memory["today_sessions_missed"] = 0
    save_user_memory(user_id, memory)

    logger.info("bowa_summary user=%s completed=%d missed=%d streak=%d", user_id, today_sessions, today_missed, current_streak)
    return {
        "completed": today_sessions,
        "missed": today_missed,
        "streak": current_streak,
        "message": message,
    }