"""Proactive engine for BOWA - initiates actions based on user state."""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from services.personality import adapt_message

NOTIFICATIONS_FILE = Path("notifications.json")

logger = logging.getLogger(__name__)


def read_notifications_store() -> dict[str, list[dict[str, Any]]]:
    """Read proactive notifications store."""
    if not NOTIFICATIONS_FILE.exists():
        return {}

    try:
        with NOTIFICATIONS_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, OSError):
        return {}

    if not isinstance(data, dict):
        return {}

    return data


def write_notifications_store(store: dict[str, list[dict[str, Any]]]) -> None:
    """Write proactive notifications to disk."""
    with NOTIFICATIONS_FILE.open("w", encoding="utf-8") as file:
        json.dump(store, file, indent=2)


def save_proactive_message(user_id: str, message: str, reason: str) -> None:
    """Save a proactive message for a user."""
    adapted_message = adapt_message(message, user_id)
    store = read_notifications_store()
    if user_id not in store:
        store[user_id] = []

    store[user_id].append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message": adapted_message,
        "reason": reason
    })

    # Keep only latest 10
    store[user_id] = store[user_id][-10:]

    write_notifications_store(store)


def get_user_notifications(user_id: str) -> list[dict[str, Any]]:
    """Get latest proactive messages for a user."""
    store = read_notifications_store()
    return store.get(user_id, [])


def generate_proactive_message(user_state: dict[str, Any]) -> tuple[str, str] | None:
    """Generate a proactive message based on user state. Returns (message, reason) or None."""
    now = datetime.now(timezone.utc)

    last_active_str = user_state.get("last_active")
    if last_active_str:
        try:
            last_active = datetime.fromisoformat(last_active_str)
            if now - last_active > timedelta(hours=24):
                return "You are breaking consistency. Start now.", "last_active > 24h"
        except ValueError:
            pass

    consistency_score = user_state.get("consistency_score")
    prev_consistency = user_state.get("prev_consistency_score")
    if consistency_score is not None and prev_consistency is not None:
        if consistency_score < prev_consistency:
            return "You are slipping. Fix today.", "consistency_dropping"

    stage = user_state.get("stage")
    progress = user_state.get("progress", 0)
    if stage == "executing" and progress == 0:
        return "Stop waiting. Do next block now.", "no_progress_in_executing"

    if consistency_score is not None and consistency_score > 0.8:  # assuming high consistency
        return "Good momentum. Increase intensity.", "consistent"

    return None


def run_proactive_checks(user_id: str, user_data: dict[str, Any]) -> None:
    """Evaluate user state and generate proactive messages if needed."""
    # Assume user_state is in user_data or need to get from state/memory
    user_state = user_data  # for now, adjust as needed

    result = generate_proactive_message(user_state)
    if result:
        message, reason = result
        save_proactive_message(user_id, message, reason)
        logger.info(f"bowa_proactive user={user_id} reason={reason} message={message}")


def trigger_execution_followup(user_id: str) -> None:
    """Trigger follow-up for expired execution session."""
    message = "Time's up! Did you complete the task? Reply 'yes' or 'no'."
    save_proactive_message(user_id, message, "execution_expired")
    logger.info(f"bowa_execution followup user={user_id}")
