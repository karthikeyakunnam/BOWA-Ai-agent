"""Background automation scheduler for BOWA."""

import hashlib
import json
import logging
import random
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from services.brain import process_user_request
from services.daily_plan import generate_daily_plan, get_active_plan_steps
from services.daily_summary import generate_daily_summary
from services.goal_engine import evaluate_goal_state, get_user_goal
from services.memory import read_memory_store, update_user_memory, load_user_memory, save_user_memory
from services.notifications import check_for_updates
from services.proactive import (
    run_proactive_checks,
    trigger_execution_followup,
    check_news_escalation,
    save_proactive_message,
    _apply_guardrails,
    _should_downgrade_tone,
)
from services.execution import (
    check_expired_sessions,
    get_execution_session,
    start_execution_session,
    create_one_session_task,
)
from services.predictor import predict_next_action, execute_prediction
from services.news_service import get_priority_news
from services.daily_news_summary import generate_daily_news_summary
from services.news_feedback import capture_user_reaction, calculate_confidence_score


RESULTS_FILE = Path("results.json")
SCHEDULER_INTERVAL_SECONDS = 300  # 5 minutes

_scheduler_thread: threading.Thread | None = None
_scheduler_lock = threading.Lock()

_results_lock = threading.Lock()
_results_store_cache = None

logger = logging.getLogger(__name__)


def read_results_store() -> dict[str, dict[str, Any]]:
    """Read saved automation results from cache/disk."""
    global _results_store_cache
    if _results_store_cache is not None:
        return _results_store_cache

    with _results_lock:
        if _results_store_cache is not None:
            return _results_store_cache

        if not RESULTS_FILE.exists():
            _results_store_cache = {}
            return _results_store_cache

        try:
            with RESULTS_FILE.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except (json.JSONDecodeError, OSError):
            _results_store_cache = {}
            return _results_store_cache

        if not isinstance(data, dict):
            _results_store_cache = {}
            return _results_store_cache

        _results_store_cache = data
        return _results_store_cache


def write_results_store(results_store: dict[str, dict[str, Any]]) -> None:
    """Write automation results to disk."""
    global _results_store_cache
    with _results_lock:
        _results_store_cache = results_store
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

    import copy
    return {
        "user_id": user_id,
        "last_update": result.get("last_update"),
        "data": copy.deepcopy(result.get("data")),
        "notifications": copy.deepcopy(result.get("notifications", []))
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


def _get_old_watch_items(user_id: str) -> list[dict[str, Any]]:
    """Get watch list items older than 24 hours that haven't been prompted."""
    memory = load_user_memory(user_id) or {}
    watch_list = memory.get("watch_list", [])
    old_items = []
    current_time = time.time()
    
    for item in watch_list:
        timestamp = item.get("timestamp", 0)
        age_hours = (current_time - timestamp) / 3600
        
        # Only consider items > 24h old and not already prompted
        if age_hours > 24 and not item.get("prompted", False):
            old_items.append(item)
    
    return old_items


def _update_watch_item_prompted(user_id: str, item_content: str) -> None:
    """Mark a watch list item as prompted to prevent duplicates."""
    memory = load_user_memory(user_id) or {}
    watch_list = memory.get("watch_list", [])
    
    for item in watch_list:
        if item.get("content") == item_content:
            item["prompted"] = True
            break
    
    save_user_memory(user_id, memory)


def _generate_watch_prompt(user_id: str, item: dict[str, Any]) -> str:
    """Generate prompt for old watch list item."""
    content = item.get("content", "")
    category = item.get("category", "General")
    urgency = item.get("urgency", "low")
    
    base_msg = f"Watched item from {category}: {content[:100]}..."
    
    if urgency == "high":
        base_msg += "\n⚠️ High urgency - consider acting now."
    
    base_msg += "\n\nStill relevant? Reply 'act' to create task or 'ignore' to remove."
    
    return base_msg


def _process_watch_list_items(user_id: str) -> None:
    """Process watch list items older than 24 hours with auto-conversion logic."""
    old_items = _get_old_watch_items(user_id)
    
    if not old_items:
        return
    
    # Process the oldest item first
    oldest_item = min(old_items, key=lambda x: x.get("timestamp", 0))
    
    # Apply guardrails before processing
    guardrails_passed, reason = _apply_guardrails(user_id, oldest_item)
    if not guardrails_passed:
        logger.info(f"bowa_watch_list blocked user={user_id} reason={reason}")
        return
    
    # Calculate confidence score
    confidence = calculate_confidence_score(user_id, oldest_item.get("category", "General"))
    urgency = oldest_item.get("urgency", "low")
    
    # Watch-to-act conversion logic
    should_convert = False
    duration = 25  # default
    
    if confidence >= 70 and urgency == "high":
        should_convert = True
        duration = random.randint(30, 45)
    elif confidence >= 40 and confidence < 70:
        should_convert = True
        duration = random.randint(20, 30)
    
    if should_convert:
        # Check for active plan before creating new session
        active_plan = get_active_plan_steps(user_id)
        if active_plan:
            # Append as next step instead of creating new session
            memory = load_user_memory(user_id) or {}
            if "daily_plan" not in memory:
                memory["daily_plan"] = {}
            
            plan = memory["daily_plan"]
            if "steps" not in plan:
                plan["steps"] = []
            
            # Check for duplicate by news_id
            news_id = hashlib.md5(oldest_item.get("content", "").encode()).hexdigest()[:8]
            existing_steps = [step for step in plan["steps"] if news_id in step.get("description", "")]
            
            if not existing_steps:
                new_step = {
                    "description": f"Act on watched item: {oldest_item.get('content', '')[:100]}...",
                    "duration": duration,
                    "category": oldest_item.get("category", "General"),
                    "news_id": news_id,
                    "source": "watch_conversion"
                }
                plan["steps"].append(new_step)
                save_user_memory(user_id, memory)
                print(f"BOWA scheduler: converted watch to plan step for {user_id}")
            return
        
        # Check for duplicate sessions by news_id
        news_id = hashlib.md5(oldest_item.get("content", "").encode()).hexdigest()[:8]
        existing_session = get_execution_session(user_id)
        
        if existing_session and existing_session.get("news_id") == news_id:
            return  # Skip duplicate
        
        # Create execution task
        task = f"Act on watched item: {oldest_item.get('content', '')[:100]}..."
        session = create_one_session_task(user_id, task, duration, source_type="watch", news_id=news_id, category=oldest_item.get("category", "General"))
        
        # Remove from watch list
        memory = load_user_memory(user_id) or {}
        watch_list = memory.get("watch_list", [])
        watch_list = [item for item in watch_list if item.get("content") != oldest_item.get("content")]
        memory["watch_list"] = watch_list
        save_user_memory(user_id, memory)
        
        # Track conversion
        capture_user_reaction(
            user_id=user_id,
            news_title=oldest_item.get("content", "")[:100],
            category=oldest_item.get("category", "General"),
            action_suggested="watch",
            user_action="auto_converted",
            goal=oldest_item.get("goal", "")
        )
        
        print(f"BOWA scheduler: auto-converted watch to task for {user_id}")
        return
    
    # Fallback to prompting if not converted
    # Check cooldown to prevent spam
    user_notifications = get_user_notifications(user_id)
    last_watch_prompt = None
    
    for notification in reversed(user_notifications):
        if notification.get("reason") == "watch_list_prompt":
            last_watch_prompt = notification
            break
    
    if last_watch_prompt:
        try:
            last_time = datetime.fromisoformat(last_watch_prompt.get("timestamp", ""))
            if datetime.now(timezone.utc) - last_time < timedelta(hours=12):  # 12-hour cooldown
                return
        except (ValueError, TypeError):
            pass
    
    # Generate and send prompt
    prompt_message = _generate_watch_prompt(user_id, oldest_item)
    
    # Downgrade tone if consistency is low
    if _should_downgrade_tone(user_id):
        prompt_message = f"Quick reminder: {oldest_item.get('content', '')[:80]}... Still relevant?"
    
    save_proactive_message(user_id, prompt_message, "watch_list_prompt", cooldown_hours=12)
    
    # Mark as prompted
    _update_watch_item_prompted(user_id, oldest_item.get("content", ""))
    
    # Track in news_feedback for analytics
    capture_user_reaction(
        user_id=user_id,
        news_title=oldest_item.get("content", "")[:100],
        category=oldest_item.get("category", "General"),
        action_suggested="watch",
        user_action="prompted",
        goal=oldest_item.get("goal", "")
    )
    
    print(f"BOWA scheduler: prompted watch list item for {user_id}")


def _apply_behavior_correction(user_id: str) -> None:
    """Apply behavior correction for missed high-urgency items from daily summary."""
    try:
        # Get yesterday's summary to check for missed items
        memory = load_user_memory(user_id) or {}
        yesterday_summary = memory.get("last_daily_summary", {})
        
        missed_items = yesterday_summary.get("what_you_missed", [])
        
        if not missed_items:
            return
        
        # Limit to top 1-2 items
        top_missed = missed_items[:2]
        
        # Check if we already applied correction today
        last_correction = memory.get("last_behavior_correction", "")
        today = datetime.now(timezone.utc).date().isoformat()
        if last_correction == today:
            return
        
        # Try to inject into active plan first
        active_plan = get_active_plan_steps(user_id)
        if active_plan:
            # Add to plan with overload protection
            if "daily_plan" not in memory:
                memory["daily_plan"] = {}
            
            plan = memory["daily_plan"]
            if "steps" not in plan:
                plan["steps"] = []
            
            current_steps = plan["steps"]
            current_step_index = memory.get("current_step_index", 0)
            
            # Limit max steps to 5
            if len(current_steps) >= 5:
                # Find and replace lowest-priority step
                lowest_priority_step = None
                lowest_priority_index = -1
                
                for i, step in enumerate(current_steps):
                    if step.get("urgency", "medium") == "low":
                        if lowest_priority_step is None or step.get("priority", 5) < lowest_priority_step.get("priority", 5):
                            lowest_priority_step = step
                            lowest_priority_index = i
                
                if lowest_priority_index >= 0:
                    # Replace the lowest priority step
                    current_steps[lowest_priority_index] = {
                        "description": f"FIX: {top_missed[0]}",
                        "duration": 25,
                        "category": "behavior_correction",
                        "source": "daily_summary_correction",
                        "urgency": "high",
                        "priority": 1  # Highest priority
                    }
                    print(f"BOWA scheduler: replaced low-priority step with correction for {user_id}")
                else:
                    # Can't inject, plan is full of high-priority items
                    print(f"BOWA scheduler: plan full, skipping correction injection for {user_id}")
            else:
                # Add corrections with deduplication
                for missed_item in top_missed:
                    # Generate news_id for deduplication
                    import hashlib
                    news_id = hashlib.md5(missed_item.encode()).hexdigest()[:8]
                    
                    # Check for duplicate by news_id
                    duplicate_exists = any(
                        step.get("news_id") == news_id or 
                        "FIX:" in step.get("description", "") and missed_item in step.get("description", "")
                        for step in current_steps
                    )
                    
                    if not duplicate_exists:
                        correction_step = {
                            "description": f"FIX: {missed_item}",
                            "duration": 25,
                            "category": "behavior_correction",
                            "source": "daily_summary_correction",
                            "urgency": "high",
                            "priority": 1,
                            "news_id": news_id
                        }
                        current_steps.append(correction_step)
                
                print(f"BOWA scheduler: added {len(top_missed)} corrections to plan for {user_id}")
            
            # Preserve current_step pointer
            memory["current_step_index"] = current_step_index
            save_user_memory(user_id, memory)
        
        else:
            # Inject into first proactive message
            correction_message = "You missed this yesterday. Fix it today:\n"
            for i, missed_item in enumerate(top_missed, 1):
                correction_message += f"{i}. {missed_item}\n"
            
            save_proactive_message(user_id, correction_message, "behavior_correction", cooldown_hours=24)
            print(f"BOWA scheduler: sent correction message for {user_id}")
        
        # Mark correction as applied
        memory["last_behavior_correction"] = today
        save_user_memory(user_id, memory)
        
    except Exception as e:
        logger.error(f"Error applying behavior correction for {user_id}: {e}")


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
            from event_timeline import append_event
            append_event(user_id, "plan_created", {"goal": plan.get("goal") if isinstance(plan, dict) else "Daily Plan", "source": "scheduler"})

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
                get_priority_news(user_data)
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

        # Run prediction only if no session was created by earlier steps
        session_after_goal = get_execution_session(user_id)
        if session_after_goal and session_after_goal.get("active"):
            logger.info("bowa_scheduler skip prediction user=%s active_session", user_id)
        else:
            prediction = predict_next_action(user_id)
            if prediction["should_act"]:
                execute_prediction(user_id, prediction)

        run_proactive_checks(user_id, user_data)
        
        # Apply behavior correction from daily summary
        _apply_behavior_correction(user_id)
        
        # Check for news escalation
        check_news_escalation(user_id)
        
        # Process watch list items older than 24 hours
        _process_watch_list_items(user_id)

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
