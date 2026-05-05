"""Decision-driven Action Engine for BOWA.

The LLM does not control product logic here. It only turns structured action
results into human-facing responses after this module has decided and executed
the next move.
"""

from __future__ import annotations

from typing import Any

from services.jobs import fetch_jobs, filter_jobs, get_skill_gap_analysis
from services.news import get_priority_news
from services.planner import build_plan, create_user_plan
from services.state import build_initial_state, update_user_state
from services.student import get_student_roadmap


ActionName = str

ASK_CLARIFICATION = "ask_clarification"
GENERATE_PLAN = "generate_plan"
SHOW_JOBS = "show_jobs"
SHOW_NEWS = "show_news"
CREATE_TRACKER = "create_tracker"
CONTINUE_FLOW = "continue_flow"
MOTIVATE_THEN_CONTINUE = "motivate_then_continue"
EXPLAIN_THEN_CONTINUE = "explain_then_continue"

VALID_ACTIONS = {
    ASK_CLARIFICATION,
    GENERATE_PLAN,
    SHOW_JOBS,
    SHOW_NEWS,
    CREATE_TRACKER,
    CONTINUE_FLOW,
    MOTIVATE_THEN_CONTINUE,
    EXPLAIN_THEN_CONTINUE,
}


def _has_context(state: dict[str, Any] | None) -> bool:
    if not state:
        return False
    if state.get("active_plan"):
        return True
    data = state.get("data", {})
    if isinstance(data, dict) and any(data.values()):
        return True
    return bool(state.get("last_action_result"))


def _looks_like_goal(message: str) -> bool:
    lowered = message.lower()
    goal_markers = [
        "i want",
        "i need",
        "my goal",
        "become",
        "learn",
        "build",
        "prepare",
        "target",
        "roadmap",
    ]
    return any(marker in lowered for marker in goal_markers)


def decide_action(
    intent: str,
    state: dict[str, Any] | None,
    message: str,
    trajectory: dict[str, Any] | None = None,
) -> ActionName:
    """Choose the next deterministic BOWA action."""
    lowered = message.lower().strip()
    trajectory_stage = (trajectory or {}).get("current_stage")

    if lowered == "next":
        return CONTINUE_FLOW

    if trajectory_stage == "unclear" and intent == "general":
        return ASK_CLARIFICATION
    if trajectory_stage == "planning" and intent in {"general", "study"}:
        return GENERATE_PLAN
    if trajectory_stage == "executing" and intent == "general":
        return CONTINUE_FLOW
    if trajectory_stage == "consistent" and intent == "general":
        return GENERATE_PLAN
    if trajectory_stage == "advanced" and intent == "general":
        return GENERATE_PLAN

    if intent == "greeting":
        return ASK_CLARIFICATION

    if "job" in lowered or "jobs" in lowered or intent == "jobs":
        return SHOW_JOBS

    if "plan my day" in lowered or "plan today" in lowered or intent == "tracker":
        return CREATE_TRACKER

    if "news" in lowered or "latest" in lowered or intent == "news":
        return SHOW_NEWS

    if _looks_like_goal(lowered) or intent == "study":
        return GENERATE_PLAN

    if _has_context(state):
        return CONTINUE_FLOW

    return ASK_CLARIFICATION


def _extract_role(message: str, state: dict[str, Any] | None) -> str:
    lowered = message.lower()
    if "frontend" in lowered:
        return "Frontend Developer"
    if "data analyst" in lowered or ("data" in lowered and "job" in lowered):
        return "Data Analyst"
    if "backend" in lowered:
        return "Backend Developer"
    if "machine learning" in lowered or "ml " in f"{lowered} ":
        return "Machine Learning Engineer"

    data = state.get("data", {}) if state else {}
    if isinstance(data, dict):
        role = data.get("role") or data.get("goal")
        if isinstance(role, str) and role.strip():
            return role.strip()

    return "Software Engineer"


def _extract_branch(message: str) -> str:
    lowered = message.lower()
    if "cse" in lowered or "computer" in lowered:
        return "CSE"
    if "ece" in lowered or "electronics" in lowered:
        return "ECE"
    if "mechanical" in lowered:
        return "Mechanical"
    if "civil" in lowered:
        return "Civil"
    return "Generic"


def _extract_hours(message: str) -> float:
    for token in message.replace(",", " ").split():
        try:
            value = float(token)
        except ValueError:
            continue
        if 0 < value <= 16:
            return value
    return 2.0


def _save_action_state(
    user_id: str,
    state: dict[str, Any] | None,
    action_result: dict[str, Any],
) -> dict[str, Any]:
    next_state = state or build_initial_state("general")
    next_state["stage"] = _next_stage(next_state.get("stage"), action_result["type"])
    next_state["last_action"] = action_result["type"]
    next_state["last_action_result"] = action_result
    if action_result["type"] == "tracker":
        next_state["mode"] = "Tracker"
        next_state["active_plan"] = action_result.get("plan")
    if action_result["type"] == "plan":
        next_state["mode"] = "Study"
        next_state["active_plan"] = {
            "goal": action_result.get("goal", ""),
            "available_hours": 2.0,
            "blocks": action_result.get("steps", []),
            "rules": [
                "Finish the current block before asking for the next one",
                "Report what you completed",
            ],
        }
    update_user_state(user_id, next_state)
    return next_state


def _next_stage(current_stage: str | None, action_type: str) -> str:
    """Progress state on every response."""
    if action_type == "clarification":
        return "ask" if current_stage != "ask" else "clarified"
    if action_type == "plan":
        return "planned"
    if action_type in {"jobs", "news", "tracker"}:
        return "executing"
    if action_type == "continue":
        return "executing"
    return "clarified"


def execute_action(
    action: ActionName,
    user_id: str,
    message: str,
    state: dict[str, Any] | None,
) -> dict[str, Any]:
    """Execute one action and return structured data for response rendering."""
    if action not in VALID_ACTIONS:
        action = ASK_CLARIFICATION

    if action == ASK_CLARIFICATION:
        result = {
            "type": "clarification",
            "question": "What are we moving forward: study, jobs, news, or today's plan?",
            "choices": ["study", "jobs", "news", "plan my day"],
        }

    elif action == MOTIVATE_THEN_CONTINUE:
        result = {
            "type": "motivation",
            "message": "Stop overthinking. Do 20 minutes. Start now.",
            "next_action": _next_from_state(state),
            "previous": state.get("last_action_result") if state else None,
        }

    elif action == EXPLAIN_THEN_CONTINUE:
        previous = state.get("last_action_result") if state else None
        previous_type = previous.get("type") if isinstance(previous, dict) else "conversation"
        result = {
            "type": "explanation",
            "message": (
                f"You are in the {previous_type} flow. "
                "I am reading your context, choosing the next action, then giving you one move."
            ),
            "next_action": _next_from_state(state),
            "previous": previous,
        }

    elif action == SHOW_JOBS:
        role = _extract_role(message, state)
        jobs = filter_jobs(fetch_jobs(), role)
        gap = get_skill_gap_analysis(role, [])
        result = {
            "type": "jobs",
            "target_role": role,
            "list": jobs[:5],
            "skill_gap": gap,
            "next_action": gap["action_plan"][0],
        }

    elif action == SHOW_NEWS:
        news = get_priority_news()
        result = {
            "type": "news",
            "list": news[:5],
            "next_action": "Pick one update that affects your study or job plan.",
        }

    elif action == CREATE_TRACKER:
        plan = create_user_plan(
            user_id=user_id,
            goal=message,
            hours=_extract_hours(message),
        )
        result = {
            "type": "tracker",
            "plan": plan,
            "next_action": plan["blocks"][0]["task"] if plan.get("blocks") else "Start now.",
        }

    elif action == GENERATE_PLAN:
        branch = _extract_branch(message)
        roadmap = get_student_roadmap(branch)
        plan = build_plan(message, _extract_hours(message))
        advanced = state and state.get("trajectory", {}).get("current_stage") == "consistent"
        steps = plan["blocks"]
        if advanced:
            steps = [
                {**step, "task": f"Advanced: {step['task']}"}
                for step in steps
            ]
        result = {
            "type": "plan",
            "goal": message,
            "roadmap": roadmap,
            "steps": steps,
            "next_action": steps[0]["task"],
        }

    else:
        previous = state.get("last_action_result") if state else None
        active_plan = state.get("active_plan") if state else None
        next_action = _advance_active_plan(active_plan) if isinstance(active_plan, dict) else None
        result = {
            "type": "continue",
            "previous": previous,
            "active_plan": active_plan,
            "next_action": next_action or _next_from_state(state),
        }

    _save_action_state(user_id, state, result)
    return result


def _advance_active_plan(plan: dict[str, Any]) -> str | None:
    """Mark the current tracker block complete and return the next block."""
    blocks = plan.get("blocks", [])
    if not isinstance(blocks, list):
        return None

    for index, block in enumerate(blocks):
        if not isinstance(block, dict):
            continue
        if not block.get("done"):
            block["done"] = True
            next_block = blocks[index + 1] if index + 1 < len(blocks) else None
            if isinstance(next_block, dict):
                return f"Do block {next_block.get('block')}: {next_block.get('task')}"
            return "Report what you finished and what blocked you."

    return "Give me the result so I can set the next target."


def _next_from_state(state: dict[str, Any] | None) -> str:
    if not state:
        return "Choose one lane: study, jobs, news, or planning."

    plan = state.get("active_plan")
    if isinstance(plan, dict):
        for block in plan.get("blocks", []):
            if not block.get("done"):
                return f"Do block {block.get('block')}: {block.get('task')}"

    previous = state.get("last_action_result")
    if isinstance(previous, dict) and previous.get("next_action"):
        return previous["next_action"]

    return "Give me your current goal and I will move you to the next step."
