"""Planning and tracker service for BOWA."""

from datetime import datetime, timezone
from typing import Any

from services.state import build_initial_state, get_user_state, update_user_state


def _split_tasks(raw_tasks: list[str] | str | None) -> list[str]:
    if raw_tasks is None:
        return []
    if isinstance(raw_tasks, str):
        raw_tasks = raw_tasks.replace("\n", ",").split(",")
    return [task.strip() for task in raw_tasks if isinstance(task, str) and task.strip()]


def build_plan(goal: str, hours: float | int | str = 2, tasks: list[str] | str | None = None) -> dict[str, Any]:
    """Build a practical study/work plan with focused blocks."""
    try:
        available_hours = max(float(hours), 0.5)
    except (TypeError, ValueError):
        available_hours = 2.0

    task_list = _split_tasks(tasks)
    if not task_list:
        task_list = [
            f"Clarify the next outcome for {goal or 'today'}",
            "Work on the highest-value task",
            "Review progress and write the next action",
        ]

    block_minutes = max(25, min(90, round((available_hours * 60) / max(len(task_list), 1))))
    blocks = [
        {
            "block": index + 1,
            "task": task,
            "duration_minutes": block_minutes,
            "done": False,
        }
        for index, task in enumerate(task_list)
    ]

    return {
        "goal": goal or "Win the day with focused execution",
        "available_hours": available_hours,
        "blocks": blocks,
        "rules": [
            "Phone away during each block",
            "One task at a time",
            "Stop after each block and mark progress",
        ],
    }


def save_plan(user_id: str, plan: dict[str, Any]) -> dict[str, Any]:
    """Persist a user's current plan in the JSON state store."""
    state = get_user_state(user_id) or build_initial_state("Tracker")
    state["mode"] = "Tracker"
    state["stage"] = "active_plan"
    state["active_plan"] = plan
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    return update_user_state(user_id, state)


def create_user_plan(
    user_id: str,
    goal: str,
    hours: float | int | str = 2,
    tasks: list[str] | str | None = None,
) -> dict[str, Any]:
    """Build and persist a planning/tracker plan for one user."""
    plan = build_plan(goal, hours, tasks)
    save_plan(user_id, plan)
    return plan


def mark_task_done(user_id: str, task_number: int) -> dict[str, Any]:
    """Mark a task block complete in the user's active plan."""
    state = get_user_state(user_id) or {}
    plan = state.get("active_plan")
    if not isinstance(plan, dict):
        return {"error": "No active plan found. Create a plan first."}

    blocks = plan.get("blocks", [])
    if not isinstance(blocks, list) or task_number < 1 or task_number > len(blocks):
        return {"error": "Invalid task number.", "active_plan": plan}

    blocks[task_number - 1]["done"] = True
    completed = sum(1 for block in blocks if block.get("done"))
    plan["progress"] = {
        "completed_blocks": completed,
        "total_blocks": len(blocks),
        "completion_percent": round((completed / len(blocks)) * 100) if blocks else 0,
    }
    save_plan(user_id, plan)
    return {"active_plan": plan}
