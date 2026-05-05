"""Intent Execution Engine for BOWA - active execution partner."""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

from services.memory import load_user_memory, save_user_memory
from services.trajectory import get_trajectory, update_trajectory
from services.trajectory import get_trajectory, update_trajectory

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


def end_execution_session(user_id: str, completed: bool) -> None:
    """End execution session and update user metrics."""
    session = get_execution_session(user_id)
    if not session:
        return

    session["status"] = "completed" if completed else "failed"
    session["active"] = False
    save_execution_session(user_id, session)

    # Update consistency score
    memory = load_user_memory(user_id) or {}
    current_score = memory.get("consistency_score", 0.5)
    if completed:
        new_score = min(1.0, current_score + 0.1)
        # Move trajectory forward
        trajectory = get_trajectory(user_id)
        if trajectory and "current_index" in trajectory:
            update_trajectory(user_id, trajectory["current_index"] + 1)
    else:
        new_score = max(0.0, current_score - 0.1)
        # Assign smaller task - could be handled in conversation

    memory["consistency_score"] = new_score
    save_user_memory(user_id, memory)

    logger.info(f"bowa_execution end user={user_id} completed={completed} new_score={new_score}")


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
    if not session:
        return {"active": False}

    start_time = datetime.fromisoformat(session["start_time"])
    elapsed = datetime.now(timezone.utc) - start_time
    remaining = max(0, session["duration"] * 60 - elapsed.total_seconds())

    return {
        "active": session["active"],
        "task": session["task"],
        "remaining_seconds": int(remaining),
        "status": session["status"]
    }</content>
<parameter name="filePath">/Users/karthikeyaunnam/bowa/services/execution.py