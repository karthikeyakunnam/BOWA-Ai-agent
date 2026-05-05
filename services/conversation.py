"""Decision-driven conversation engine for BOWA.

Flow:
User -> detect intent -> decide action -> execute action -> render response.

The LLM never controls logic. It only converts structured action results into
sharp BOWA-style language.
"""

import json
import logging
from typing import Any, Generator

from services.actions import (
    CONTINUE_FLOW,
    EXPLAIN_THEN_CONTINUE,
    MOTIVATE_THEN_CONTINUE,
    decide_action,
    execute_action,
)
from services.execution import (
    check_expired_sessions,
    end_execution_session,
    get_execution_session,
    start_execution_session,
)
from services.memory import load_user_memory, save_user_memory
from services.personality import adapt_message
from services.formatter import format_response
from services.llm import generate_response, llm_available
from services.response_builder import build_response
from services.action_selector import decide_next_action
from services.planner_engine import generate_plan
from services.state import build_initial_state, get_user_state, update_user_state
from services.trajectory import load_trajectory, update_trajectory
from services.vector_memory import add_memory, retrieve_memory, get_relevant_memory
from services.reflection import analyze_performance
from services.strategy import choose_strategy


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


def analyze_user_state(message: str, state: dict[str, Any] | None) -> dict[str, str]:
    """Reason about user state before choosing an action."""
    lowered = message.lower().strip()
    intent = detect_intent(message)

    lazy_markers = ["don't feel", "dont feel", "lazy", "tired", "exhausted", "no energy"]
    confused_markers = ["what is this", "what's this", "confused", "i don't understand", "dont understand"]
    urgency_markers = ["urgent", "today", "now", "deadline", "asap", "tomorrow"]
    clear_goal_markers = ["i want", "i need", "my goal", "become", "learn", "build", "prepare", "plan my day"]

    if _looks_like(lowered, lazy_markers):
        mood = "lazy"
    elif _looks_like(lowered, confused_markers):
        mood = "confused"
    elif _looks_like(lowered, clear_goal_markers) or intent in {"jobs", "study", "tracker", "news"}:
        mood = "focused"
    else:
        mood = "curious"

    if _looks_like(lowered, clear_goal_markers) or intent in {"jobs", "study", "tracker", "news"} or lowered == "next":
        clarity = "clear"
    else:
        clarity = "vague"

    if _looks_like(lowered, ["urgent", "asap", "deadline", "right now"]):
        urgency = "high"
    elif _looks_like(lowered, urgency_markers):
        urgency = "medium"
    else:
        urgency = "low"

    if state and state.get("last_action_result") and lowered in {"next", "continue", "ok", "done"}:
        clarity = "clear"
        mood = "focused" if mood != "lazy" else mood

    return {
        "intent": intent,
        "mood": mood,
        "clarity": clarity,
        "urgency": urgency,
    }


def _select_action_from_reason(
    reason: dict[str, str],
    state: dict[str, Any] | None,
    message: str,
    trajectory: dict[str, Any] | None = None,
) -> str:
    """Let reasoning steer the deterministic action choice."""
    if reason["mood"] == "lazy":
        return MOTIVATE_THEN_CONTINUE
    if reason["mood"] == "confused":
        return EXPLAIN_THEN_CONTINUE
    if reason["clarity"] == "vague":
        return "ask_clarification"
    return decide_action(reason["intent"], state, message, trajectory)


def _trajectory_context_lines(action_result: dict[str, Any]) -> list[str]:
    """Return response context from trajectory."""
    trajectory = action_result.get("trajectory")
    if not isinstance(trajectory, dict):
        return []

    stage = trajectory.get("current_stage", "unclear")
    score = trajectory.get("consistency_score", 0)
    feedback = trajectory.get("feedback", "")
    stage_labels = {
        "unclear": "You're in unclear phase.",
        "planning": "You're in planning phase.",
        "executing": "You're in execution phase.",
        "consistent": "You're building consistency.",
        "advanced": "You're ready for harder work.",
    }

    lines = [stage_labels.get(stage, "You're in progress.")]
    if feedback:
        lines.append(feedback)
    lines.append(f"Consistency: {score}/100")
    return lines


def _render_without_llm(action_result: dict[str, Any]) -> str:
    """Deterministic renderer for offline mode."""
    result_type = action_result.get("type")
    context_lines = _trajectory_context_lines(action_result)

    if result_type == "clarification":
        choices = ", ".join(action_result.get("choices", []))
        return "\n".join([
            *context_lines,
            f"{action_result.get('question')}",
            f"Pick one: {choices}.",
        ])

    if result_type == "motivation":
        return "\n".join([
            *context_lines,
            action_result.get("message", "Stop overthinking. Start small."),
            f"Next: {action_result.get('next_action')}",
        ])

    if result_type == "explanation":
        return "\n".join([
            *context_lines,
            action_result.get("message", "I am using your context to pick the next action."),
            f"Next: {action_result.get('next_action')}",
        ])

    if result_type == "jobs":
        lines = [*context_lines, f"Target role: **{action_result.get('target_role')}**"]
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
            return "\n".join([
                *context_lines,
                "No live news configured.",
                "Next: add `NEWS_API_KEY` or ask for jobs, study, or planning.",
            ])
        lines = [*context_lines, "Priority news:"]
        for item in news[:3]:
            lines.append(f"- [{item.get('priority')}] {item.get('title')}")
        lines.append(f"Next: {action_result.get('next_action')}")
        return "\n".join(lines)

    if result_type == "tracker":
        plan = action_result.get("plan", {})
        lines = [*context_lines, f"Plan: **{plan.get('goal')}**"]
        for block in plan.get("blocks", [])[:4]:
            lines.append(f"- {block.get('duration_minutes')} min: {block.get('task')}")
        lines.append(f"Start: {action_result.get('next_action')}")
        return "\n".join(lines)

    if result_type == "plan":
        lines = [*context_lines, f"Goal: **{action_result.get('goal')}**"]
        for step in action_result.get("steps", [])[:4]:
            lines.append(f"- {step.get('duration_minutes')} min: {step.get('task')}")
        lines.append(f"Start: {action_result.get('next_action')}")
        return "\n".join(lines)

    lines = [*context_lines, "Continue from where you stopped."]
    lines.append(f"Do next: {action_result.get('next_action')}")
    return "\n".join(lines)


def _render_with_llm(
    action_result: dict[str, Any],
    state: dict[str, Any] | None,
    semantic_context: list[str],
) -> str:
    """Use LLM only to convert structured action data into human response."""
    deterministic_reply = _render_without_llm(action_result)
    llm_reply = generate_response(
        context={
            "state": state or {},
            "semantic_context": semantic_context[:3],
            "action_type": action_result.get("type"),
        },
        structured_data=deterministic_reply,
    )
    return llm_reply or deterministic_reply


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


def handle_unclear_input(
    message: str,
    state: dict[str, Any] | None,
    user_id: str,
) -> dict[str, Any]:
    """Fallback handler for loops, vague input, and context questions."""
    lowered = message.lower().strip()

    if lowered == "next":
        return execute_action(CONTINUE_FLOW, user_id, message, state)

    if lowered in {"what is this", "what's this", "what are you doing"}:
        previous = state.get("last_action_result") if state else None
        previous_type = previous.get("type") if isinstance(previous, dict) else "conversation"
        result = {
            "type": "clarification",
            "question": (
                f"You are in the {previous_type} flow. "
                "I am trying to define your next concrete step."
            ),
            "choices": ["say next", "give goal", "ask jobs", "plan my day"],
            "next_action": "Reply with `next` or give me the exact thing you want.",
        }
        _save_fallback_state(user_id, state, result)
        return result

    result = {
        "type": "clarification",
        "question": "Be specific. What exactly do you want next?",
        "choices": ["generate plan", "show jobs", "show news", "create tracker"],
        "next_action": "Give me one clear target.",
    }
    _save_fallback_state(user_id, state, result)
    return result


def _save_fallback_state(
    user_id: str,
    state: dict[str, Any] | None,
    action_result: dict[str, Any],
) -> None:
    next_state = state or build_initial_state("general")
    current_stage = next_state.get("stage")
    next_state["stage"] = "clarified" if current_stage == "ask" else "ask"
    next_state["last_action"] = action_result["type"]
    next_state["last_action_result"] = action_result
    update_user_state(user_id, next_state)


def _set_last_reply(user_id: str, reply: str) -> dict[str, Any]:
    """Persist last reply for loop detection."""
    state = get_user_state(user_id) or build_initial_state("general")
    state["last_reply"] = reply
    return update_user_state(user_id, state)


def _force_stage_progress(user_id: str, previous_stage: str | None) -> None:
    """Guarantee each turn changes the stage marker."""
    state = get_user_state(user_id) or build_initial_state("general")
    current_stage = state.get("stage")
    if current_stage != previous_stage:
        return

    progress_count = int(state.get("progress_count", 0)) + 1
    state["progress_count"] = progress_count

    if current_stage == "ask":
        state["stage"] = "clarified"
    elif current_stage == "clarified":
        state["stage"] = "planned"
    elif current_stage == "planned":
        state["stage"] = "executing"
    elif current_stage == "executing" or str(current_stage).startswith("executing_"):
        state["stage"] = f"executing_{progress_count}"
    else:
        state["stage"] = "ask"

    update_user_state(user_id, state)


def handle_user_message(
    user_id: str,
    message: str,
    mode: str = "General",
) -> dict[str, Any]:
    """Process one BOWA turn through the Action Engine."""
    # Inject continuity context
    memory = load_user_memory(user_id) or {}
    last_goal = memory.get("last_goal")
    last_topic = memory.get("last_topic")
    intent = detect_intent(message, mode)

    if last_goal and intent in ["study", "tracker"] and last_goal not in message.lower():
        message = f"You were working on {last_goal} earlier. {message}"

    # Check for execution follow-up
    session = get_execution_session(user_id)
    if session and session.get("status") == "expired":
        lowered = message.lower().strip()
        if lowered in ["yes", "y", "completed", "done"]:
            end_execution_session(user_id, True)
            reply = "Great! Consistency boosted. What's next?"
        elif lowered in ["no", "n", "not yet", "failed"]:
            end_execution_session(user_id, False)
            reply = "Okay, let's break it down. Start with 10 minutes."
        else:
            reply = "Did you complete the task? Reply 'yes' or 'no'."
        reply = adapt_message(reply, user_id)
        return {"reply": reply, "action": "execution_followup", "reason": "execution_followup", "state": get_user_state(user_id), "structured": {}}

    state = get_user_state(user_id)
    previous_stage = state.get("stage") if state else None
    history = _get_conversation_history(user_id)
    semantic_context = get_relevant_memory(user_id, message)
    trajectory = load_trajectory(user_id)
    state_for_reason = {**(state or {}), "user_id": user_id, "trajectory": trajectory}
    
    last_action = state_for_reason.get("last_action", "none")
    reflection = analyze_performance(state_for_reason, last_action, message)
    state_for_reason["reflection"] = reflection

    strategy_data = choose_strategy(state_for_reason, reflection, intent)

    plan = generate_plan(state_for_reason, intent, message)
    if plan:
        state_for_reason["active_plan"] = plan
        update_user_state(user_id, state_for_reason)
        logger.info("bowa_plan steps=%d current=%d", plan["total_steps"], plan["current_step"])

    lowered = message.lower().strip()
    reason = analyze_user_state(message, state_for_reason)
    intent = reason["intent"]
    if lowered in {"what is this", "what's this", "what are you doing"}:
        action = EXPLAIN_THEN_CONTINUE
        action_result = execute_action(action, user_id, message, state_for_reason)
    else:
        if state_for_reason.get("active_plan"):
            action = "execute_plan_step"
        else:
            action = _select_action_from_reason(reason, state_for_reason, message, trajectory)
        action_result = execute_action(action, user_id, message, state_for_reason)

    if action == "execute_plan_step":
        plan = state_for_reason.get("active_plan")
        current_step = plan["steps"][plan["current_step"] - 1]
        action_result = {
            "type": "plan_step",
            "message": f"Step {plan['current_step']}: {current_step['action']}",
            "next_action": "Complete this step and report back",
            "plan_step": plan["current_step"],
            "total_steps": plan["total_steps"]
        }

    trajectory = update_trajectory({**(get_user_state(user_id) or {}), "user_id": user_id}, action_result)
    action_result["trajectory"] = trajectory
    state_after_trajectory = get_user_state(user_id) or build_initial_state("general")
    state_after_trajectory["trajectory"] = trajectory
    update_user_state(user_id, state_after_trajectory)

    # Dynamic Action Selection
    selected_action = decide_next_action(state_after_trajectory, intent, {"user_message": message})
    logger.info("bowa_action action=%s intent=%s", selected_action, intent)

    if selected_action != "continue":
        if selected_action == "motivate":
            action_result = execute_action(MOTIVATE_THEN_CONTINUE, user_id, message, state_for_reason)
        elif selected_action == "simplify":
            action_result = execute_action(EXPLAIN_THEN_CONTINUE, user_id, message, state_for_reason)
        elif selected_action == "switch_to_jobs":
            action_result = execute_action("jobs", user_id, message, state_for_reason)
        elif selected_action == "switch_to_study":
            action_result = execute_action("study", user_id, message, state_for_reason)
        elif selected_action == "plan":
            action_result = execute_action("tracker", user_id, message, state_for_reason)
        elif selected_action == "push":
            action_result = execute_action(MOTIVATE_THEN_CONTINUE, user_id, message, state_for_reason)
        # For ask_clarification, keep as is

    if llm_available():
        deterministic_reply = _render_without_llm(action_result)
        structured_data = build_response(state_after_trajectory, intent, deterministic_reply, strategy_data, reflection)
        structured_data["action"] = selected_action
        logger.info(
            "bowa_structured stage=%s tone=%s next=%s",
            structured_data.get("stage"),
            structured_data.get("tone"),
            structured_data.get("next_step"),
        )
        raw_reply = generate_response(
            context=state_after_trajectory,
            structured_data=structured_data,
        )
    else:
        raw_reply = _render_without_llm(action_result)

    reply = format_response(raw_reply)
    if llm_available():
        logger.info("bowa_llm intent=%s tools=groq reply=%s", intent, reply)

    latest_state = get_user_state(user_id) or state
    if latest_state and reply == latest_state.get("last_reply"):
        action_result = handle_unclear_input(message, latest_state, user_id)
        if llm_available():
            raw_reply = _render_with_llm(action_result, message, semantic_context)
        else:
            raw_reply = _render_without_llm(action_result)
        reply = format_response(raw_reply)

    reply = _avoid_repeat(reply, history, action_result)
    if latest_state and reply == latest_state.get("last_reply"):
        action_result = handle_unclear_input("vague", latest_state, user_id)
        reply = format_response(_render_without_llm(action_result))

    history.append({"role": "user", "content": message})
    history.append({"role": "assistant", "content": reply})
    _save_conversation_history(user_id, history)
    _set_last_reply(user_id, reply)
    _force_stage_progress(user_id, previous_stage)

    add_memory(user_id, message, role="user")
    add_memory(user_id, reply, role="assistant")

    # Update interaction count for personality
    memory = load_user_memory(user_id) or {}
    memory["interaction_count"] = memory.get("interaction_count", 0) + 1
    memory["last_topic"] = intent
    if "become" in message.lower() or "goal" in message.lower():
        # Simple extraction
        words = message.split()
        for i, word in enumerate(words):
            if word.lower() in ["become", "goal"]:
                memory["last_goal"] = " ".join(words[i+1:i+4])  # next few words
                break
    save_user_memory(user_id, memory)

    logger.info(
        "bowa_reason=%s action=%s trajectory_stage=%s consistency_score=%s final_reply=%r",
        reason,
        action,
        trajectory.get("current_stage"),
        trajectory.get("consistency_score"),
        reply,
    )

    # Check for execution triggers
    lowered = message.lower().strip()
    if _looks_like(lowered, ["start", "do it", "begin", "plan my day", "let's start", "execute"]):
        task = "Execute your current plan"  # or extract from message/context
        start_execution_session(user_id, task)
        reply += "\n\n⏰ Session started: 25 minutes. Go!"

    reply = adapt_message(reply, user_id)

    return {
        "reply": reply,
        "action": action_result.get("type", action),
        "reason": reason,
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
