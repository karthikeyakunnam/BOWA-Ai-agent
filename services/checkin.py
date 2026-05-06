"""Daily check-in system for BOWA.

Generates personalized check-in messages for daily habit reinforcement.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from services.goal_engine import get_user_goal
from services.memory import load_user_memory
from services.streak import get_user_streak

logger = logging.getLogger(__name__)


def generate_checkin(user_state: dict[str, Any]) -> dict[str, Any]:
    """Generate a daily check-in based on user state."""
    user_id = user_state.get("user_id", "unknown")
    goal = get_user_goal(user_id)
    streak = get_user_streak(user_id)
    current_streak = streak["current_streak"]
    memory = load_user_memory(user_id) or {}
    last_active = memory.get("last_active_date")

    today = datetime.now(timezone.utc).date().isoformat()
    yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()

    if not goal:
        status = "starting"
        message = "Welcome back. Set a goal to get started."
        today_focus = "Define your main goal"
        urgency = "low"
    elif last_active == today:
        # Already active today
        status = "active"
        message = f"You're on track today. Streak: {current_streak} days."
        today_focus = goal
        urgency = "medium"
    elif last_active == yesterday and current_streak > 0:
        # On streak, reinforce
        status = "on_track"
        message = f"You're on a {current_streak}-day streak. Keep it going!"
        today_focus = goal
        urgency = "high"
    elif last_active and datetime.fromisoformat(last_active).date() < datetime.now(timezone.utc).date() - timedelta(days=1):
        # Missed yesterday, recovery
        status = "behind"
        message = "You missed yesterday. Restart your streak today."
        today_focus = goal
        urgency = "high"
    else:
        # New or irregular
        status = "starting"
        message = "Let's build a habit. Start today."
        today_focus = goal
        urgency = "medium"

    logger.info("bowa_checkin user=%s status=%s urgency=%s", user_id, status, urgency)
    return {
        "status": status,
        "message": message,
        "today_focus": today_focus,
        "urgency": urgency,
    }