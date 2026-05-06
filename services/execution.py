"""Intent Execution Engine for BOWA - active execution partner."""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

from services.event_bus import emit_event
from services.goal_engine import evaluate_goal_state, record_goal_session
from services.memory import load_user_memory, save_user_memory
from services.reflection import analyze_performance
from services.reward import generate_reward
from services.streak import update_streak
from services.strategy import choose_strategy
from services.trajectory import load_trajectory, update_trajectory
from services.llm import generate_response

EXECUTION_SESSIONS_FILE = Path("execution_sessions.json")

logger = logging.getLogger(__name__)


def read_execution_sessions() -> dict[str, dict[str, Any]]:
    """Read execution sessions store."""
    if not EXECUTION_SESSIONS_FILE.exists():
        return {}

    try:
        with EXECUTION_SESSIONS_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, OSError):
        return {}

    if not isinstance(data, dict):
        return {}

    return data


def write_execution_sessions(sessions: dict[str, dict[str, Any]]) -> None:
    """Write execution sessions to disk."""
    with EXECUTION_SESSIONS_FILE.open("w", encoding="utf-8") as file:
        json.dump(sessions, file, indent=2)


def get_execution_session(user_id: str) -> dict[str, Any] | None:
    """Get current execution session for a user."""
    sessions = read_execution_sessions()
    session = sessions.get(user_id)
    if not session:
        return None

    # Check if expired
    start_time = datetime.fromisoformat(session.get("start_time", ""))
    duration = session.get("duration", 25)
    if datetime.now(timezone.utc) - start_time > timedelta(minutes=duration):
        if session.get("status") == "running":
            session["status"] = "expired"
            save_execution_session(user_id, session)

    return session


def save_execution_session(user_id: str, session: dict[str, Any]) -> None:
    """Save execution session for a user."""
    sessions = read_execution_sessions()
    sessions[user_id] = session
    write_execution_sessions(sessions)


def start_execution_session(user_id: str, task: str, duration: int = 25) -> dict[str, Any]:
    """Start a new execution session."""
    existing = get_execution_session(user_id)
    if existing and existing.get("active") and existing.get("status") == "running":
        logger.info(
            "bowa_execution start skipped user=%s already_running",
            user_id,
        )
        return existing

    session = {
        "active": True,
        "task": task,
        "duration": duration,
        "start_time": datetime.now(timezone.utc).isoformat(),
        "status": "running"
    }
    save_execution_session(user_id, session)
    logger.info(f"bowa_execution start user={user_id} task={task} duration={duration}")
    return session


def handle_session_completion(user_id: str, completed: bool, session: dict[str, Any]) -> None:
    """Complete execution session and persist analysis + strategy."""
    duration = session.get("duration", 25)
    status = "completed" if completed else "incomplete"
    summary = f"Session: {duration}min {status}"

    memory = load_user_memory(user_id) or {}
    current_score = memory.get("consistency_score", 0.5)
    new_score = min(1.0, current_score + 0.1) if completed else max(0.0, current_score - 0.1)

    memory["last_session_summary"] = summary
    memory["last_active"] = session.get("start_time") or datetime.now(timezone.utc).isoformat()
    memory["prev_consistency_score"] = current_score
    memory["consistency_score"] = new_score

    record_goal_session(user_id, completed)
    goal_state = evaluate_goal_state(user_id)
    memory["goal_progress"] = int(goal_state.get("goal_progress", "0%").replace("%", ""))

    # Update streak
    streak_data = update_streak(user_id, completed)
    memory["current_streak"] = streak_data["current_streak"]
    memory["longest_streak"] = streak_data["longest_streak"]

    # Update progress visualization data
    total_sessions = memory.get("total_sessions", 0) + 1
    memory["total_sessions"] = total_sessions
    success_rate = (memory.get("total_sessions_completed", 0) / total_sessions) * 100 if total_sessions > 0 else 0
    memory["success_rate"] = success_rate

    state = {
        "trajectory": load_trajectory(user_id),
        "mood": memory.get("mood", "neutral"),
        "user_id": user_id,
    }
    reflection = analyze_performance(state, session.get("task", ""), summary)
    strategy_data = choose_strategy(state, reflection, "general")

    memory["last_reflection"] = reflection
    memory["last_strategy"] = strategy_data

    # Generate reward
    reward = generate_reward(state, {"completed": completed})
    memory["last_reward"] = reward

    save_user_memory(user_id, memory)

    update_trajectory({"user_id": user_id}, {"type": "continue", "next_action": summary})

    emit_event(user_id, "execution_complete", {
        "result": "success" if completed else "failure",
        "next_step": summary,
        "reward": reward,
        "streak": streak_data["current_streak"],
    })


def end_execution_session(user_id: str, completed: bool) -> None:
    """End execution session and update user metrics."""
    session = get_execution_session(user_id)
    if not session:
        return

    session["status"] = "completed" if completed else "failed"
    session["active"] = False
    save_execution_session(user_id, session)

    handle_session_completion(user_id, completed, session)

    logger.info(
        "bowa_execution end user=%s completed=%s new_score=%s",
        user_id,
        completed,
        load_user_memory(user_id).get("consistency_score", 0.0),
    )


def check_expired_sessions() -> list[tuple[str, dict[str, Any]]]:
    """Check for expired sessions and return them for follow-up."""
    sessions = read_execution_sessions()
    expired = []

    for user_id, session in sessions.items():
        if session.get("active") and session.get("status") == "running":
            start_time = datetime.fromisoformat(session.get("start_time", ""))
            duration = session.get("duration", 25)
            if datetime.now(timezone.utc) - start_time > timedelta(minutes=duration):
                session["status"] = "expired"
                save_execution_session(user_id, session)
                expired.append((user_id, session))

    return expired


def get_session_status(user_id: str) -> dict[str, Any]:
    """Get execution session status for UI."""
    session = get_execution_session(user_id)
    memory = load_user_memory(user_id) or {}
    last_session = memory.get("last_session_summary", "")

    if not session:
        return {"active": False, "last_session": last_session}

    start_time = datetime.fromisoformat(session["start_time"])
    elapsed = datetime.now(timezone.utc) - start_time
    remaining = max(0, session["duration"] * 60 - elapsed.total_seconds())

    return {
        "active": session["active"],
        "task": session["task"],
        "remaining_seconds": int(remaining),
        "status": session["status"],
        "last_session": last_session
    }
