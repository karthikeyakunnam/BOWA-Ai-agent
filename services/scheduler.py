"""Background automation scheduler for BOWA."""

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.brain import process_user_request
from services.daily_plan import generate_daily_plan
from services.daily_summary import generate_daily_summary
from services.goal_engine import evaluate_goal_state, get_user_goal
from services.memory import read_memory_store
from services.notifications import check_for_updates
from services.proactive import run_proactive_checks, trigger_execution_followup
from services.execution import check_expired_sessions, get_execution_session, start_execution_session
from services.predictor import predict_next_action, execute_prediction
from services.news_service import get_priority_news
from services.daily_news_summary import generate_daily_news_summary
from services.memory import update_user_memory


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


def should_generate_daily_plan(user_id: str, user_data: dict[str, Any]) -> bool:
    """Decide if a daily plan should be created for a user."""
    goal = user_data.get("goal") or user_data.get("last_goal")
    if not goal:
        return False

    daily_plan = user_data.get("daily_plan") or {}
    generated_at = daily_plan.get("created_at")
    if not generated_at:
        return True

    try:
        generated_date = datetime.fromisoformat(generated_at).date()
    except ValueError:
        return True

    return generated_date < datetime.now(timezone.utc).date()


def evaluate_and_restart_goal(user_id: str) -> None:
    """Check goal progress and trigger an execution session if the user is behind schedule."""
    goal_state = evaluate_goal_state(user_id)
    gap_value = int(goal_state.get("gap", "0").split()[0])
    urgency = goal_state.get("urgency", "low")
    session = get_execution_session(user_id)

    if session and session.get("active"):
        return

    if gap_value >= 2 or urgency == "high":
        start_execution_session(
            user_id,
            f"Refocus on your goal: {goal_state.get('goal', 'Continue progress')}"
        )
        return

    if urgency == "medium":
        start_execution_session(
            user_id,
            f"Continue progress on your goal: {goal_state.get('goal', 'Keep moving')}"
        )


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

        if should_generate_daily_plan(user_id, user_data):
            plan = generate_daily_plan(user_id)
            user_data["daily_plan"] = plan

        evaluate_and_restart_goal(user_id)

        request_data = {
            **user_data,
            "user_id": user_id
        }
        response = process_user_request(request_data)

        old_result = previous_results.get(user_id, {})
        old_data = old_result.get("data", {}) if isinstance(old_result, dict) else {}
        notifications = check_for_updates(old_data, response)

        # News Refresh Frequency (Task 4)
        frequency_map = {"30min": 1800, "1hr": 3600, "2hr": 7200, "3hr": 10800, "6hr": 21600}
        user_freq = user_data.get("news_frequency", "3hr")
        freq_seconds = frequency_map.get(user_freq, 10800)
        
        last_news_fetch = user_data.get("last_news_fetch", 0)
        current_time = time.time()
        
        if current_time - last_news_fetch >= freq_seconds:
            try:
                get_priority_news()
                user_data["last_news_fetch"] = current_time
                update_user_memory(user_id, user_data)
                print(f"BOWA scheduler: fetched news for {user_id}")
            except Exception as e:
                print(f"BOWA scheduler failed to fetch news: {e}")

        # End of day news summary (Task 5)
        now_utc = datetime.now(timezone.utc)
        if now_utc.hour == 20: # 20:00 UTC
            last_summary = user_data.get("last_daily_news_summary_date")
            if last_summary != now_utc.date().isoformat():
                news_summary = generate_daily_news_summary(user_id)
                msg = "🔥 TODAY SUMMARY\n"
                
                if news_summary.get("key_takeaways"):
                    msg += "\n🔑 Key Takeaways:\n"
                    for item in news_summary["key_takeaways"]: msg += f"- {item}\n"
                    
                if news_summary.get("impact_for_user"):
                    msg += "\n🎯 Impact for YOU:\n"
                    for item in news_summary["impact_for_user"]: msg += f"- {item}\n"
                    
                if news_summary.get("what_you_should_do"):
                    msg += "\n⚡ What you should do:\n"
                    for item in news_summary["what_you_should_do"]: msg += f"- {item}\n"
                
                notifications.append({"user_id": user_id, "message": msg, "type": "daily_news_summary"})
                user_data["last_daily_news_summary_date"] = now_utc.date().isoformat()
                update_user_memory(user_id, user_data)

        trigger_notifications(notifications)

        save_user_result(user_id, response, notifications)
        processed_results[user_id] = response
        print(f"BOWA scheduler: processed user {user_id}")

        # Run prediction before proactive checks
        prediction = predict_next_action(user_id)
        if prediction["should_act"]:
            execute_prediction(user_id, prediction)

        run_proactive_checks(user_id, user_data)

        # Check for expired execution sessions
        expired = check_expired_sessions()
        for exp_user_id, _ in expired:
            if exp_user_id == user_id:
                trigger_execution_followup(user_id)

        # Generate daily summary at end of day (simplified: every run, but could be time-based)
        summary = generate_daily_summary(user_id)
        print(f"BOWA daily summary for {user_id}: {summary['message']}")

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
