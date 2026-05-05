"""Background automation scheduler for BOWA."""

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.brain import process_user_request
from services.memory import read_memory_store
from services.notifications import check_for_updates
from services.proactive import run_proactive_checks, trigger_execution_followup
from services.execution import check_expired_sessions


RESULTS_FILE = Path("results.json")
SCHEDULER_INTERVAL_SECONDS = 30

_scheduler_thread: threading.Thread | None = None
_scheduler_lock = threading.Lock()


def read_results_store() -> dict[str, dict[str, Any]]:
    """Read saved automation results."""
    if not RESULTS_FILE.exists():
        return {}

    try:
        with RESULTS_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, OSError):
        return {}

    if not isinstance(data, dict):
        return {}

    return data


def write_results_store(results_store: dict[str, dict[str, Any]]) -> None:
    """Write automation results to disk."""
    with RESULTS_FILE.open("w", encoding="utf-8") as file:
        json.dump(results_store, file, indent=2)


def get_latest_user_result(user_id: str) -> dict[str, Any]:
    """Return the latest stored scheduler result for one user."""
    results_store = read_results_store()
    result = results_store.get(user_id)

    if not isinstance(result, dict):
        return {
            "user_id": user_id,
            "last_update": None,
            "data": None,
            "notifications": []
        }

    return {
        "user_id": user_id,
        "last_update": result.get("last_update"),
        "data": result.get("data"),
        "notifications": result.get("notifications", [])
    }


def merge_recent_notifications(
    existing_notifications: list[dict[str, str]],
    new_notifications: list[dict[str, str]]
) -> list[dict[str, str]]:
    """Keep a compact recent notification history."""
    return (new_notifications + existing_notifications)[:10]


def save_user_result(
    user_id: str,
    data: dict[str, Any],
    notifications: list[dict[str, str]] | None = None
) -> None:
    """Save the latest BOWA output for one user."""
    results_store = read_results_store()
    previous_result = results_store.get(user_id, {})
    existing_notifications = []

    if isinstance(previous_result, dict):
        existing_notifications = previous_result.get("notifications", [])

    recent_notifications = merge_recent_notifications(
        existing_notifications,
        notifications or []
    )

    results_store[user_id] = {
        "last_update": datetime.now(timezone.utc).isoformat(),
        "data": data,
        "notifications": recent_notifications
    }
    write_results_store(results_store)


def trigger_notifications(notifications: list[dict[str, str]]) -> None:
    """Print generated notifications to the console."""
    for notification in notifications:
        print("🔥 NOTIFICATION:")
        print(f"User {notification['user_id']} → {notification['message']}")


def run_bowa_for_all_users() -> dict[str, dict[str, Any]]:
    """Run BOWA processing for every user in memory."""
    memory_store = read_memory_store()
    previous_results = read_results_store()
    processed_results = {}

    if not memory_store:
        print("BOWA scheduler: no users found in memory")
        return processed_results

    for user_id, user_data in memory_store.items():
        if not isinstance(user_data, dict):
            continue

        request_data = {
            **user_data,
            "user_id": user_id
        }
        response = process_user_request(request_data)

        old_result = previous_results.get(user_id, {})
        old_data = old_result.get("data", {}) if isinstance(old_result, dict) else {}
        notifications = check_for_updates(old_data, response)
        trigger_notifications(notifications)

        save_user_result(user_id, response, notifications)
        processed_results[user_id] = response
        print(f"BOWA scheduler: processed user {user_id}")

        run_proactive_checks(user_id, user_data)

        # Check for expired execution sessions
        expired = check_expired_sessions()
        for exp_user_id, _ in expired:
            if exp_user_id == user_id:
                trigger_execution_followup(user_id)

    return processed_results


def scheduler_loop() -> None:
    """Run BOWA automation forever in a background thread."""
    while True:
        try:
            run_bowa_for_all_users()
        except Exception as exc:
            print(f"BOWA scheduler error: {exc}")

        time.sleep(SCHEDULER_INTERVAL_SECONDS)


def start_scheduler() -> None:
    """Start the background scheduler once."""
    global _scheduler_thread

    with _scheduler_lock:
        if _scheduler_thread and _scheduler_thread.is_alive():
            return

        _scheduler_thread = threading.Thread(
            target=scheduler_loop,
            name="bowa-scheduler",
            daemon=True
        )
        _scheduler_thread.start()
        print(
            "BOWA scheduler started "
            f"(interval: {SCHEDULER_INTERVAL_SECONDS} seconds)"
        )
