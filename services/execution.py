"""Intent Execution Engine for BOWA - active execution partner."""

import json
import logging
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

from services.event_bus import emit_event
from services.goal_engine import evaluate_goal_state, record_goal_session
from services.memory import load_user_memory, save_user_memory
from services.reward import generate_reward
from services.streak import update_streak
from services.strategy import choose_strategy
from services.trajectory import load_trajectory, update_trajectory
from services.reflection import analyze_performance
from services.llm import generate_response

import threading

EXECUTION_SESSIONS_FILE = Path("execution_sessions.json")
_execution_lock = threading.Lock()
_execution_store_cache = None
logger = logging.getLogger(__name__)


def read_execution_sessions() -> dict[str, dict[str, Any]]:
    """Read execution sessions store."""
    global _execution_store_cache
    if _execution_store_cache is not None:
        return _execution_store_cache

    with _execution_lock:
        if _execution_store_cache is not None:
            return _execution_store_cache

        if not EXECUTION_SESSIONS_FILE.exists():
            _execution_store_cache = {}
            return _execution_store_cache

        try:
            with EXECUTION_SESSIONS_FILE.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except (json.JSONDecodeError, OSError):
            _execution_store_cache = {}
            return _execution_store_cache

        if not isinstance(data, dict):
            _execution_store_cache = {}
            return _execution_store_cache

        _execution_store_cache = data
        return _execution_store_cache


def write_execution_sessions(sessions: dict[str, dict[str, Any]]) -> None:
    """Write execution sessions to disk."""
    global _execution_store_cache
    with _execution_lock:
        _execution_store_cache = sessions
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

    import copy
    return copy.deepcopy(session)


def save_execution_session(user_id: str, session: dict[str, Any]) -> None:
    """Save execution session for a user."""
    sessions = read_execution_sessions()
    import copy
    sessions[user_id] = copy.deepcopy(session)
    write_execution_sessions(sessions)


def _calculate_adjusted_duration(user_id: str, source_type: str, default_duration: int = 25) -> int:
    """Calculate adjusted duration based on user performance."""
    if source_type != "news":
        return default_duration
    
    memory = load_user_memory(user_id) or {}
    stats = memory.get("news_action_stats", {})
    consistency_score = memory.get("consistency_score", 0.5)
    
    success_rate = stats.get("success_rate", 50) / 100  # Convert to decimal
    
    if success_rate < 0.4:
        return random.randint(10, 20)
    elif 0.4 <= success_rate <= 0.7:
        return random.randint(20, 30)
    else:
        return random.randint(30, 45)


def create_one_session_task(user_id: str, task: str, duration: int = 25, source_type: str = "general", news_id: str = "", category: str = "") -> dict[str, Any]:
    """Create a 1-session task."""
    existing = get_execution_session(user_id)
    if existing and existing.get("active") and existing.get("status") == "running":
        logger.info(
            "bowa_execution start skipped user=%s already_running",
            user_id,
        )
        return existing

    # Apply duration adjustment for news-triggered tasks
    adjusted_duration = _calculate_adjusted_duration(user_id, source_type, duration)

    session = {
        "active": True,
        "task": task,
        "duration": adjusted_duration,
        "start_time": datetime.now(timezone.utc).isoformat(),
        "status": "running",
        "source_type": source_type,
        "news_id": news_id,
        "category": category
    }
    save_execution_session(user_id, session)
    from event_timeline import append_event
    append_event(
        user_id,
        "execution_started",
        {
            "task": task,
            "duration": adjusted_duration,
            "source_type": source_type,
            "news_id": news_id,
            "category": category,
        }
    )
    logger.info(f"bowa_execution start user={user_id} task={task} duration={adjusted_duration} source={source_type}")
    return session


def start_execution_session(user_id: str, task: str, duration: int = 25, source_type: str = "general", news_id: str = "", category: str = "") -> dict[str, Any]:
    """Alias for create_one_session_task used by other services."""
    return create_one_session_task(user_id, task, duration, source_type, news_id, category)


def _is_news_triggered_task(task: str) -> bool:
    """Check if execution task was triggered by news."""
    return "Act on news:" in task or "news:" in task.lower()


def _update_news_follow_through(user_id: str, task: str, completed: bool) -> None:
    """Update follow_through status for news-triggered tasks."""
    # Import here to avoid circular import
    from services.news_feedback import _get_news_feedback_history, _save_news_feedback_history
    
    history = _get_news_feedback_history(user_id)
    
    # Find the relevant news entry
    for news_id, entry in reversed(history.items()):
        if (entry.get("action_suggested") == "act" and 
            entry.get("follow_through") is None and
            "Act on news:" in task):
            
            entry["follow_through"] = completed
            _save_news_feedback_history(user_id, history)
            break


def _classify_news_task_outcome(session: dict[str, Any], user_confirmed: bool = None) -> str:
    """Classify news task outcome: completed/partial/abandoned."""
    if session.get("source_type") != "news":
        return "completed"  # Non-news tasks use existing logic
    
    duration = session.get("duration", 25)
    start_time = session.get("start_time")
    
    if not start_time:
        return "abandoned"
    
    try:
        start_dt = datetime.fromisoformat(start_time)
        actual_duration = (datetime.now(timezone.utc) - start_dt).total_seconds() / 60
        completion_percentage = min(100, (actual_duration / duration) * 100)
    except (ValueError, TypeError):
        return "abandoned"
    
    # User confirmation takes precedence
    if user_confirmed is True:
        return "completed"
    elif user_confirmed is False:
        return "abandoned"
    
    # Duration-based classification
    if completion_percentage >= 100:
        return "completed"
    elif completion_percentage >= 50:
        return "partial"
    else:
        return "abandoned"


def _infer_impact_from_outcome(outcome: str, user_id: str) -> str:
    """Infer impact from completion status and engagement patterns."""
    memory = load_user_memory(user_id) or {}
    stats = memory.get("news_action_stats", {})
    
    # Check for repeated engagement (completed actions)
    completed_count = stats.get("completed_actions", 0)
    total_count = stats.get("total_actions", 0)
    
    if outcome == "completed":
        if completed_count >= 3 and total_count > 0:  # Repeated engagement
            return "high"
        else:
            return "medium"
    elif outcome == "partial":
        return "medium"
    elif outcome == "abandoned":
        return "low"
    
    return "medium"  # default


def _update_confidence_from_impact(user_id: str, impact: str) -> None:
    """Update confidence_score based on impact evaluation."""
    memory = load_user_memory(user_id) or {}
    
    # Get current confidence or initialize
    current_confidence = memory.get("confidence_score", 50)
    
    # Adjust confidence based on impact
    if impact == "high":
        current_confidence = min(100, current_confidence + 10)
    elif impact == "medium":
        current_confidence = max(30, min(80, current_confidence + 5))
    elif impact == "low":
        current_confidence = max(10, current_confidence - 5)
    
    memory["confidence_score"] = current_confidence
    save_user_memory(user_id, memory)


def _update_news_action_stats(user_id: str, outcome: str, source_type: str = "news") -> None:
    """Update user stats for news-triggered actions with outcome classification."""
    # Only count source_type="news" tasks
    if source_type != "news":
        return
    
    memory = load_user_memory(user_id) or {}
    
    # Initialize stats if not present
    if "news_action_stats" not in memory:
        memory["news_action_stats"] = {
            "total_actions": 0,
            "completed_actions": 0,
            "partial_actions": 0,
            "abandoned_actions": 0,
            "success_rate": 0.0,
            "impact_score": 50,  # default neutral impact
            "last_impact": "medium"
        }
    
    stats = memory["news_action_stats"]
    stats["total_actions"] += 1
    
    # Update outcome counters
    if outcome == "completed":
        stats["completed_actions"] += 1
    elif outcome == "partial":
        stats["partial_actions"] += 1
    elif outcome == "abandoned":
        stats["abandoned_actions"] += 1
    
    # Calculate success rate (completed/total)
    if stats["total_actions"] > 0:
        stats["success_rate"] = (stats["completed_actions"] / stats["total_actions"]) * 100
    
    # Infer and store impact
    impact = _infer_impact_from_outcome(outcome, user_id)
    stats["last_impact"] = impact
    
    # Update impact_score (weighted average)
    if stats["total_actions"] == 1:
        stats["impact_score"] = {"high": 80, "medium": 50, "low": 20}[impact]
    else:
        # Weighted average with more weight on recent actions
        new_score = {"high": 80, "medium": 50, "low": 20}[impact]
        stats["impact_score"] = int((stats["impact_score"] * 0.7) + (new_score * 0.3))
    
    save_user_memory(user_id, memory)
    
    # Update confidence_score from impact
    _update_confidence_from_impact(user_id, impact)


def handle_session_completion(user_id: str, completed: bool, session: dict[str, Any]) -> None:
    """Complete execution session and persist analysis + strategy."""
    duration = session.get("duration", 25)
    status = "completed" if completed else "incomplete"
    summary = f"Session: {duration}min {status}"
    
    # Classify outcome for news tasks
    outcome = _classify_news_task_outcome(session, user_confirmed=completed)
    
    # Track news-triggered task completion
    task = session.get("task", "")
    source_type = session.get("source_type", "general")
    if source_type == "news":
        _update_news_follow_through(user_id, task, completed)
        _update_news_action_stats(user_id, outcome, source_type)
    elif _is_news_triggered_task(task):  # Backward compatibility
        _update_news_follow_through(user_id, task, completed)
        _update_news_action_stats(user_id, outcome, "news")

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
    from event_timeline import append_event
    append_event(
        user_id,
        "execution_completed",
        {
            "task": session.get("task"),
            "completed": completed,
            "status": session["status"]
        }
    )

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
                from event_timeline import append_event
                append_event(
                    user_id,
                    "execution_completed",
                    {
                        "task": session.get("task"),
                        "completed": False,
                        "status": "expired"
                    }
                )
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
