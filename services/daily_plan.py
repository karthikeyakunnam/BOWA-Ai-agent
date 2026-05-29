"""Daily plan generator for BOWA.

Creates a lightweight daily task list based on the user's goal and progress.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from services.goal_engine import evaluate_goal_state, get_user_goal
from services.memory import load_user_memory, save_user_memory

logger = logging.getLogger(__name__)


def _build_tasks(goal: str, urgency: str) -> list[str]:
    tasks = []
    base = goal or "your current goal"

    if urgency == "high":
        tasks = [
            f"Review the top 3 steps for {base}",
            f"Do the hardest one for 30 minutes",
            f"Write down what blocked you and remove it",
        ]
    elif urgency == "medium":
        tasks = [
            f"Pick one key action for {base}",
            f"Work on it for 25 minutes",
            "Summarize your progress and next step",
        ]
    else:
        tasks = [
            f"Clarify one good step for {base}",
            "Start with the easiest high-impact task",
            "Finish with a short review and next target",
        ]

    return tasks


def generate_daily_plan(user_id: str) -> dict[str, Any]:
    """Generate and persist a daily plan for the user."""
    goal_state = evaluate_goal_state(user_id)
    goal = get_user_goal(user_id) or "Focus work"
    urgency = goal_state.get("urgency", "low")
    tasks = _build_tasks(goal, urgency)
    duration = 60 if urgency == "high" else 45 if urgency == "medium" else 30
    priority = "highest" if urgency == "high" else "important" if urgency == "medium" else "normal"
    plan = {
        "tasks": tasks,
        "priority": priority,
        "duration": duration,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "urgency": urgency,
    }

    memory = load_user_memory(user_id) or {}
    memory["daily_plan"] = plan
    memory["daily_plan_generated_at"] = plan["created_at"]
    save_user_memory(user_id, memory)

    logger.info("bowa_daily_plan created user=%s urgency=%s", user_id, urgency)
    return plan


def get_active_plan_steps(user_id: str) -> list[dict[str, Any]] | None:
    """Get active plan steps for a user if valid for today."""
    memory = load_user_memory(user_id) or {}
    plan = memory.get("daily_plan")
    if not plan:
        return None

    created_at = plan.get("created_at")
    if not created_at:
        return None

    try:
        created_date = datetime.fromisoformat(created_at).date()
        if created_date < datetime.now(timezone.utc).date():
            return None
    except ValueError:
        return None

    # In this implementation, tasks are just strings. 
    # Converting to list of dicts if that's what's expected.
    tasks = plan.get("tasks", [])
    if not tasks:
        return None
        
    return [{"task": task} for task in tasks]
