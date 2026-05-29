"""Centralized event timeline system for BOWA.

Stores and retrieves chronological events for each user.
"""

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TIMELINE_FILE = Path("event_timeline.json")
_timeline_lock = threading.Lock()
_timeline_store_cache = None
logger = logging.getLogger(__name__)


def read_timeline_store() -> dict[str, list[dict[str, Any]]]:
    """Read the event timeline store from disk."""
    global _timeline_store_cache
    if _timeline_store_cache is not None:
        return _timeline_store_cache

    with _timeline_lock:
        if _timeline_store_cache is not None:
            return _timeline_store_cache

        if not TIMELINE_FILE.exists():
            _timeline_store_cache = {}
            return _timeline_store_cache
        try:
            with TIMELINE_FILE.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except (json.JSONDecodeError, OSError):
            _timeline_store_cache = {}
            return _timeline_store_cache
        if not isinstance(data, dict):
            _timeline_store_cache = {}
            return _timeline_store_cache
        _timeline_store_cache = data
        return _timeline_store_cache


def write_timeline_store(store: dict[str, list[dict[str, Any]]]) -> None:
    """Write the event timeline store to disk."""
    global _timeline_store_cache
    with _timeline_lock:
        _timeline_store_cache = store
        with TIMELINE_FILE.open("w", encoding="utf-8") as file:
            json.dump(store, file, indent=2)


def append_event(user_id: str, event_type: str, metadata: dict[str, Any] | None = None) -> None:
    """Append a new event to the timeline for a user."""
    if not user_id:
        user_id = "default"

    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
        "event_type": event_type,
        "metadata": metadata or {}
    }

    store = read_timeline_store()
    if user_id not in store:
        store[user_id] = []

    store[user_id].append(event)
    # Keep only latest 100 events
    store[user_id] = store[user_id][-100:]

    write_timeline_store(store)
    logger.info("bowa_event_timeline user=%s type=%s", user_id, event_type)


def get_user_timeline(user_id: str) -> list[dict[str, Any]]:
    """Return the latest 100 events for a user."""
    store = read_timeline_store()
    return store.get(user_id, [])


# ---------------------------------------------------------------------------
# Dynamic Interceptors (Inversion of Control for non-listed files / modules)
# ---------------------------------------------------------------------------
def _setup_interceptors() -> None:
    # 1. Intercept set_user_goal in goal_engine.py
    try:
        import services.goal_engine
        original_set_goal = services.goal_engine.set_user_goal

        def wrapped_set_goal(user_id: str, goal: str) -> dict[str, Any]:
            res = original_set_goal(user_id, goal)
            append_event(user_id, "goal_updated", {"goal": goal})
            return res

        services.goal_engine.set_user_goal = wrapped_set_goal
    except Exception as e:
        logger.warning("Failed to setup goal interceptor: %s", e)

    # 2. Intercept save_proactive_message in proactive.py (notification_sent)
    try:
        import services.proactive
        original_save_proactive = services.proactive.save_proactive_message

        def wrapped_save_proactive(user_id: str, message: str, reason: str, cooldown_hours: int = 6) -> None:
            store_before = services.proactive.read_notifications_store()
            notifs_before = store_before.get(user_id, [])
            last_before = notifs_before[-1] if notifs_before else None

            original_save_proactive(user_id, message, reason, cooldown_hours)

            store_after = services.proactive.read_notifications_store()
            notifs_after = store_after.get(user_id, [])
            last_after = notifs_after[-1] if notifs_after else None

            if last_after and (last_before is None or last_after.get("timestamp") != last_before.get("timestamp")):
                append_event(user_id, "notification_sent", {
                    "message": last_after.get("message"),
                    "reason": last_after.get("reason")
                })

        services.proactive.save_proactive_message = wrapped_save_proactive
    except Exception as e:
        logger.warning("Failed to setup proactive interceptor: %s", e)

    # 3. Intercept update_user_state in state.py (plan_created, plan_completed)
    try:
        import services.state
        original_update_state = services.state.update_user_state

        def wrapped_update_state(user_id: str, state: dict[str, Any]) -> dict[str, Any]:
            old_state = services.state.get_user_state(user_id) or {}
            new_state = original_update_state(user_id, state)

            old_plan = old_state.get("active_plan")
            new_plan = new_state.get("active_plan")

            if isinstance(new_plan, dict):
                is_created = False
                if not isinstance(old_plan, dict):
                    is_created = True
                else:
                    if (old_plan.get("goal") != new_plan.get("goal") or
                            old_plan.get("steps") != new_plan.get("steps") or
                            old_plan.get("blocks") != new_plan.get("blocks")):
                        is_created = True

                if is_created:
                    source = "general"
                    if "steps" in new_plan:
                        source = "planner_engine"
                    elif "blocks" in new_plan:
                        source = "tracker"
                    append_event(user_id, "plan_created", {
                        "goal": new_plan.get("goal"),
                        "source": source
                    })

                if new_plan.get("completed") and (not isinstance(old_plan, dict) or not old_plan.get("completed")):
                    append_event(user_id, "plan_completed", {
                        "goal": new_plan.get("goal")
                    })

            return new_state

        services.state.update_user_state = wrapped_update_state
    except Exception as e:
        logger.warning("Failed to setup state interceptor: %s", e)


_setup_interceptors()
