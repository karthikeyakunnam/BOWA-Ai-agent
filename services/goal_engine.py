"""Goal engine for BOWA.

Provides centralized goal storage and evaluation for user progress tracking.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from services.memory import load_user_memory, save_user_memory

logger = logging.getLogger(__name__)


def get_user_goal(user_id: str) -> str | None:
    """Return the user's current goal, if any."""
    from services.state import get_user_state, update_user_state, get_active_mode

    # Load active mode state
    state = get_user_state(user_id)
    if state and state.get("data", {}).get("goal"):
        return state["data"]["goal"]

    # Migration fallback
    memory = load_user_memory(user_id) or {}
    global_goal = memory.get("goal") or memory.get("last_goal")
    if global_goal:
        if not state:
            from services.state import build_initial_state
            active_mode = get_active_mode(user_id)
            state = build_initial_state(active_mode)
        state.setdefault("data", {})
        state["data"]["goal"] = global_goal.strip()
        update_user_state(user_id, state)
        return global_goal

    return None


def set_user_goal(user_id: str, goal: str) -> dict[str, Any]:
    """Save a user's goal into persistent memory."""
    from services.state import get_user_state, update_user_state, build_initial_state, get_active_mode

    cleaned_goal = goal.strip()

    # 1. Update active mode state
    active_mode = get_active_mode(user_id)
    state = get_user_state(user_id) or build_initial_state(active_mode)
    state.setdefault("data", {})
    state["data"]["goal"] = cleaned_goal
    update_user_state(user_id, state)

    # 2. Update memory.json for statistics & backwards compatibility
    memory = load_user_memory(user_id) or {}
    memory["goal_set_at"] = datetime.now(timezone.utc).isoformat()
    memory.setdefault("total_sessions_completed", 0)
    memory.setdefault("total_sessions_missed", 0)
    memory.setdefault("goal_progress", 0)
    save_user_memory(user_id, memory)
    logger.info("bowa_goal set user=%s goal=%s", user_id, cleaned_goal)
    return memory





def evaluate_goal_state(user_id: str) -> dict[str, Any]:
    """Evaluate current goal progress, urgency, and schedule gap."""
    memory = load_user_memory(user_id) or {}
    goal = get_user_goal(user_id)
    if not goal:
        return {
            "goal": "",
            "expected_progress": "0 sessions",
            "actual_progress": "0 sessions",
            "gap": "0",
            "urgency": "low",
        }

    created = memory.get("goal_set_at")
    if created:
        try:
            started = datetime.fromisoformat(created)
        except ValueError:
            started = datetime.now(timezone.utc)
    else:
        started = datetime.now(timezone.utc)

    days_active = max(1, (datetime.now(timezone.utc) - started).days + 1)
    expected_sessions = days_active * 1
    completed = int(memory.get("total_sessions_completed", 0))
    missed = int(memory.get("total_sessions_missed", 0))
    actual_progress = completed
    progress_ratio = min(1.0, actual_progress / max(1, expected_sessions))
    gap_value = expected_sessions - actual_progress

    if gap_value >= 2 or missed >= 1:
        urgency = "high"
    elif gap_value == 1:
        urgency = "medium"
    else:
        urgency = "low"

    goal_progress = int(progress_ratio * 100)
    memory["goal_progress"] = goal_progress
    save_user_memory(user_id, memory)

    return {
        "goal": goal,
        "expected_progress": f"{expected_sessions} sessions",
        "actual_progress": f"{actual_progress} sessions",
        "gap": f"{gap_value} sessions",
        "urgency": urgency,
        "goal_progress": f"{goal_progress}%",
        "days_active": days_active,
        "missed_sessions": missed,
    }


def record_goal_session(user_id: str, completed: bool) -> None:
    """Update goal session counts after each execution session."""
    memory = load_user_memory(user_id) or {}
    if completed:
        memory["total_sessions_completed"] = int(memory.get("total_sessions_completed", 0)) + 1
    else:
        memory["total_sessions_missed"] = int(memory.get("total_sessions_missed", 0)) + 1
    save_user_memory(user_id, memory)
