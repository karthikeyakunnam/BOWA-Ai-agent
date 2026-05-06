"""Weekly insight engine for BOWA.

Analyzes user patterns and provides actionable insights.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from services.memory import load_user_memory

logger = logging.getLogger(__name__)


def generate_weekly_insight(user_id: str) -> dict[str, Any]:
    """Generate weekly insights for the user."""
    memory = load_user_memory(user_id) or {}
    total_sessions = memory.get("total_sessions", 0)
    completed = memory.get("total_sessions_completed", 0)
    missed = memory.get("total_sessions_missed", 0)
    success_rate = memory.get("success_rate", 0)
    current_streak = memory.get("current_streak", 0)
    longest_streak = memory.get("longest_streak", 0)

    # Simple trend analysis
    if success_rate > 70:
        trend = "improving"
    elif success_rate > 50:
        trend = "steady"
    else:
        trend = "declining"

    # Identify weakness
    if missed > completed:
        weakness = "completion rate"
        suggestion = "Focus on finishing sessions rather than starting them."
    elif current_streak < 3:
        weakness = "consistency"
        suggestion = "Build daily habits by setting smaller, achievable goals."
    else:
        weakness = "progress tracking"
        suggestion = "Track your goals more closely to stay motivated."

    insight = {
        "consistency_trend": trend,
        "success_rate": f"{success_rate:.1f}%",
        "biggest_weakness": weakness,
        "suggestion": suggestion,
        "current_streak": current_streak,
        "longest_streak": longest_streak,
    }

    logger.info("bowa_insight user=%s trend=%s weakness=%s", user_id, trend, weakness)
    return insight