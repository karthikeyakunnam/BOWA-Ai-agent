"""Decision-driven conversation engine for BOWA.

Flow:
User -> detect intent -> decide action -> execute action -> render response.

The LLM never controls logic. It only converts structured action results into
sharp BOWA-style language.
"""

import json
import logging
from typing import Any, Generator

from services.actions import decide_action, execute_action
from services.formatter import format_response
from services.llm import generate_response, llm_available
from services.state import build_initial_state, get_user_state, update_user_state
from services.vector_memory import add_memory, retrieve_memory


logger = logging.getLogger(__name__)


def _get_conversation_history(user_id: str) -> list[dict[str, Any]]:
    """Retrieve short-term conversation history from state.json."""
    state = get_user_state(user_id)
    if not state or "history" not in state:
        return []
    history = state["history"]
    return history if isinstance(history, list) else []


def _save_conversation_history(user_id: str, history: list[dict[str, Any]]) -> None:
    """Save compact short-term conversation history without resetting state."""
    state = get_user_state(user_id) or build_initial_state("general")
    state["history"] = history[-10:]
    update_user_state(user_id, state)


def _looks_like(text: str, keywords: list[str]) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in keywords)


def detect_intent(message: str, mode: str = "General") -> str:
    """Detect intent from message first, with mode as a weak hint."""
    lowered = message.lower().strip()

    if lowered in {"hi", "hello", "hey", "yo", "sup"}:
        return "greeting"

    if _looks_like(lowered, ["job", "jobs", "intern", "career", "hiring", "role"]):
        return "jobs"
    if _looks_like(lowered, ["plan my day", "plan today", "tracker", "schedule today"]):
        return "tracker"
    if _looks_like(lowered, ["news", "latest", "headline", "market update"]):
        return "news"
    if _looks_like(lowered, ["study", "roadmap", "learn", "prepare", "cse", "ece"]):
        return "study"

    mode_map = {
        "Jobs": "jobs",
        "Tracker": "tracker",
        "News": "news",
        "Study": "study",
    }
    return mode_map.get(mode, "general")


def _render_without_llm(action_result: dict[str, Any]) -> str:
    """Deterministic renderer for offline mode."""
    result_type = action_result.get("type")

    if result_type == "clarification":
        choices = ", ".join(action_result.get("choices", []))
        return f"{action_result.get('question')}\nPick one: {choices}."

    if result_type == "jobs":
        lines = [f"Target role: **{action_result.get('target_role')}**"]
        for job in action_result.get("list", [])[:3]:
            lines.append(f"- {job.get('role')} at {job.get('company')} ({job.get('location')})")
        missing = action_result.get("skill_gap", {}).get("missing_skills", [])
        if missing:
            lines.append(f"Next skill: **{missing[0]}**")
        lines.append(f"Next: {action_result.get('next_action')}")
        return "\n".join(lines)

    if result_type == "news":
        news = action_result.get("list", [])
        if not news:
            return "No live news configured.\nNext: add `NEWS_API_KEY` or ask for jobs, study, or planning."
        lines = ["Priority news:"]
        for item in news[:3]:
            lines.append(f"- [{item.get('priority')}] {item.get('title')}")
        lines.append(f"Next: {action_result.get('next_action')}")
        return "\n".join(lines)

    if result_type == "tracker":
        plan = action_result.get("plan", {})
        lines = [f"Plan: **{plan.get('goal')}**"]
        for block in plan.get("blocks", [])[:4]:
            lines.append(f"- {block.get('duration_minutes')} min: {block.get('task')}")
        lines.append(f"Start: {action_result.get('next_action')}")
        return "\n".join(lines)

    if result_type == "plan":
        lines = [f"Goal: **{action_result.get('goal')}**"]
        for step in action_result.get("steps", [])[:4]:
            lines.append(f"- {step.get('duration_minutes')} min: {step.get('task')}")
        lines.append(f"Start: {action_result.get('next_action')}")
        return "\n".join(lines)

    lines = ["Continue from where you stopped."]
    lines.append(f"Next: {action_result.get('next_action')}")
    return "\n".join(lines)


def _render_with_llm(
    action_result: dict[str, Any],
    message: str,
    semantic_context: list[str],
) -> str:
    """Use LLM only to convert structured action data into human response."""
    messages = [
        {
            "role": "system",
            "content": (
                "Convert this structured BOWA action into a sharp, motivating response. "
                "Do not change facts. Do not invent data. Keep it under 8 lines. "
                "Always include the action result's concrete data and next_action."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "user_message": message,
                    "semantic_context": semantic_context[:3],
                    "action_result": action_result,
                },
                ensure_ascii=True,
            ),
        },
    ]
    response = generate_response(messages)
    return response.get("content") or _render_without_llm(action_result)


def _avoid_repeat(reply: str, history: list[dict[str, Any]], action_result: dict[str, Any]) -> str:
    """Ensure BOWA never returns the exact same message twice."""
    previous_replies = [
        item.get("content", "")
        for item in history
        if item.get("role") == "assistant"
    ]
    if reply not in previous_replies:
        return reply

    next_action = action_result.get("next_action") or "Give me the result of your last step."
    return format_response(
        f"Same context, next move changes.\nNext: {next_action}\nDo it, then report back with what happened."
    )


def handle_user_message(
    user_id: str,
    message: str,
    mode: str = "General",
) -> dict[str, Any]:
    """Process one BOWA turn through the Action Engine."""
    state = get_user_state(user_id)
    history = _get_conversation_history(user_id)
    semantic_context = retrieve_memory(user_id, message)

    intent = detect_intent(message, mode)
    action = decide_action(intent, state, message)
    action_result = execute_action(action, user_id, message, state)

    if llm_available():
        raw_reply = _render_with_llm(action_result, message, semantic_context)
    else:
        raw_reply = _render_without_llm(action_result)

    reply = format_response(raw_reply)
    reply = _avoid_repeat(reply, history, action_result)

    history.append({"role": "user", "content": message})
    history.append({"role": "assistant", "content": reply})
    _save_conversation_history(user_id, history)

    add_memory(user_id, message, role="user")
    add_memory(user_id, reply, role="assistant")

    logger.info(
        "bowa_action intent=%s action=%s final_reply=%r",
        intent,
        action,
        reply,
    )

    return {
        "reply": reply,
        "action": action_result.get("type", action),
        "state": get_user_state(user_id),
        "structured": action_result,
    }


def handle_user_message_stream(
    user_id: str,
    message: str,
    mode: str = "General",
) -> Generator[str, None, None]:
    """Stream a completed Action Engine response in small chunks."""
    result = handle_user_message(user_id, message, mode)
    reply = result["reply"]
    for index in range(0, len(reply), 24):
        yield reply[index:index + 24]
