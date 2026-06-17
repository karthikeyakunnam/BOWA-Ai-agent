"""Trajectory Engine for BOWA.

Tracks user progress over time so BOWA responds from the user's journey, not
from a blank conversation each turn.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from services.memory import load_user_memory, save_user_memory


TRAJECTORY_STAGES = {
    "stage_1": "unclear",
    "stage_2": "planning",
    "stage_3": "executing",
    "stage_4": "consistent",
    "stage_5": "advanced",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _default_trajectory(user_id: str) -> dict[str, Any]:
    return {
        "user_id": user_id,
        "goal": "",
        "current_stage": "unclear",
        "completed_steps": [],
        "last_active": "",
        "consistency_score": 0,
        "hesitation_count": 0,
        "feedback": "",
    }


def load_trajectory(user_id: str) -> dict[str, Any]:
    """Load trajectory fields from memory.json."""
    memory = load_user_memory(user_id)
    trajectory = _default_trajectory(user_id)

    for key in trajectory:
        if key in memory:
            trajectory[key] = memory[key]

    # Dynamically inject current goal from goal_engine
    from services.goal_engine import get_user_goal
    trajectory["goal"] = get_user_goal(user_id) or ""

    # Dynamically resolve current_stage if executing
    try:
        from services.execution import get_execution_session
        session = get_execution_session(user_id)
        if session and session.get("active") and session.get("status") == "running":
            trajectory["current_stage"] = "executing"
        elif trajectory.get("current_stage") == "executing":
            trajectory["current_stage"] = "planning"
    except Exception:
        pass

    return trajectory




def _infer_goal(action_result: dict[str, Any], previous_goal: str) -> str:
    if action_result.get("goal"):
        return str(action_result["goal"])

    plan = action_result.get("plan")
    if isinstance(plan, dict) and plan.get("goal"):
        return str(plan["goal"])

    if action_result.get("target_role"):
        return str(action_result["target_role"])

    return previous_goal


def _stage_from_action(
    action_type: str,
    consistency_score: float,
    completed_count: int,
    hesitation_count: int,
) -> str:
    if action_type == "clarification":
        return "unclear"
    if hesitation_count >= 2:
        return "unclear"
    if action_type == "plan":
        return "planning"
    if action_type == "plan_step":
        return "executing"
    
    # Information-oriented action types stay in planning phase
    if action_type in {"jobs", "news", "explanation", "motivation"}:
        return "planning"

    if action_type in {"tracker", "continue"}:
        # Only enter executing phase if they have at least one started/completed step
        if completed_count >= 1:
            if consistency_score >= 0.70 and completed_count >= 3:
                return "advanced"
            if consistency_score >= 0.45 and completed_count >= 2:
                return "consistent"
            return "executing"
        return "planning"

    return "planning"


def update_trajectory(
    state: dict[str, Any] | None,
    action_result: dict[str, Any],
) -> dict[str, Any]:
    """Update persistent trajectory after an action.

    Rules:
    - completed/continued work moves the user forward
    - idle gaps reduce consistency
    - repeated hesitation keeps the user in unclear stage but changes approach
    """
    user_id = str((state or {}).get("user_id") or "default")
    trajectory = load_trajectory(user_id)
    previous_active = _parse_time(trajectory.get("last_active"))
    now = _now()
    action_type = str(action_result.get("type", "clarification"))

    consistency_score = float(trajectory.get("consistency_score", 0.0))
    feedback = "Good. Keep the streak."

    if previous_active:
        gap_hours = (now - previous_active).total_seconds() / 3600
        if gap_hours >= 36:
            consistency_score = max(0.0, consistency_score - 0.15)
            feedback = "You're losing consistency. Reset today."
        elif gap_hours <= 30:
            consistency_score = min(1.0, consistency_score + 0.08)
    else:
        consistency_score = min(1.0, consistency_score + 0.05)

    hesitation_count = int(trajectory.get("hesitation_count", 0))
    if action_type in {"clarification", "motivation", "explanation"}:
        hesitation_count += 1
    else:
        hesitation_count = 0

    completed_steps = trajectory.get("completed_steps", [])
    if not isinstance(completed_steps, list):
        completed_steps = []

    next_action = action_result.get("next_action")
    if action_type == "continue" and next_action:
        completed_steps.append(str(next_action))
    elif action_type in {"tracker", "plan"} and next_action:
        completed_steps.append(f"started: {next_action}")
    elif action_type == "plan_step":
        completed_steps.append(f"plan_step:{action_result.get('plan_step', '1')}")

    completed_steps = completed_steps[-20:]
    current_stage = _stage_from_action(
        action_type,
        consistency_score,
        len(completed_steps),
        hesitation_count,
    )

    from services.goal_engine import get_user_goal, set_user_goal
    current_goal = get_user_goal(user_id) or ""
    new_goal = _infer_goal(action_result, current_goal)
    if new_goal and new_goal != current_goal:
        set_user_goal(user_id, new_goal)

    trajectory.update({
        "goal": new_goal,
        "current_stage": current_stage,
        "completed_steps": completed_steps,
        "last_active": now.isoformat(),
        "consistency_score": consistency_score,
        "hesitation_count": hesitation_count,
        "feedback": feedback,
    })

    memory = load_user_memory(user_id)
    memory.update(trajectory)
    save_user_memory(user_id, memory)
    return trajectory

