"""Proactive engine for BOWA - initiates actions based on user state."""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from services.event_bus import emit_event
from services.personality import adapt_message
from services.news_feedback import _get_news_feedback_history, _save_news_feedback_history
from services.memory import load_user_memory, save_user_memory
from services.execution import get_execution_session

import threading

NOTIFICATIONS_FILE = Path("notifications.json")
_notifications_lock = threading.Lock()
_notifications_store_cache = None

logger = logging.getLogger(__name__)


def read_notifications_store() -> dict[str, list[dict[str, Any]]]:
    """Read proactive notifications store."""
    global _notifications_store_cache
    if _notifications_store_cache is not None:
        return _notifications_store_cache

    with _notifications_lock:
        if _notifications_store_cache is not None:
            return _notifications_store_cache

        if not NOTIFICATIONS_FILE.exists():
            _notifications_store_cache = {}
            return _notifications_store_cache

        try:
            with NOTIFICATIONS_FILE.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except (json.JSONDecodeError, OSError):
            _notifications_store_cache = {}
            return _notifications_store_cache

        if not isinstance(data, dict):
            _notifications_store_cache = {}
            return _notifications_store_cache

        _notifications_store_cache = data
        return _notifications_store_cache


def write_notifications_store(store: dict[str, list[dict[str, Any]]]) -> None:
    """Write proactive notifications to disk."""
    global _notifications_store_cache
    with _notifications_lock:
        _notifications_store_cache = store
        with NOTIFICATIONS_FILE.open("w", encoding="utf-8") as file:
            json.dump(store, file, indent=2)


def _get_last_notification_time(user_notifications: list[dict[str, Any]]) -> datetime | None:
    if not user_notifications:
        return None
    try:
        last_timestamp = user_notifications[-1].get("timestamp")
        return datetime.fromisoformat(last_timestamp) if last_timestamp else None
    except (ValueError, TypeError):
        return None


def _calculate_adaptive_cooldown(user_id: str, base_cooldown: int = 6) -> int:
    """Calculate adaptive cooldown based on user activity and completion."""
    memory = load_user_memory(user_id) or {}
    
    last_active_str = memory.get("last_active")
    if not last_active_str:
        return base_cooldown

    try:
        last_active = datetime.fromisoformat(last_active_str)
    except (ValueError, TypeError):
        return base_cooldown

    # Check if a notification was already sent after the user's last activity
    store = read_notifications_store()
    user_notifications = store.get(user_id, [])
    if user_notifications:
        try:
            last_notif_time = datetime.fromisoformat(user_notifications[-1].get("timestamp", ""))
            # If a notification has been sent since last_active, enforce standard cooldown
            if last_notif_time > last_active:
                return base_cooldown
        except (ValueError, TypeError):
            pass

    # Check if user completed a task in last 6 hours
    hours_since_active = (datetime.now(timezone.utc) - last_active).total_seconds() / 3600
    
    if hours_since_active <= 6:
        # User was recently active/completed a task
        return base_cooldown * 2  # Double cooldown to 12h
    
    if hours_since_active > 24:
        # Allow 1 immediate nudge for inactive user
        return 0  # No cooldown

    return base_cooldown


def is_proactive_cooldown_active(user_id: str, reason: str, cooldown_hours: int = 6) -> bool:
    """Check if the cooldown for the given reason is active or if daily limit is reached."""
    store = read_notifications_store()
    user_notifications = store.get(user_id, [])
    
    # Check daily message limit (never exceed 2 messages/day)
    today = datetime.now(timezone.utc).date()
    today_count = 0
    for notification in user_notifications:
        try:
            ts = notification.get("timestamp", "")
            if ts and datetime.fromisoformat(ts).date() == today:
                today_count += 1
        except (ValueError, TypeError):
            continue
            
    if today_count >= 2:
        logger.info(f"bowa_proactive blocked user={user_id} reason={reason} daily_limit")
        return True
        
    # Calculate adaptive cooldown
    adaptive_cooldown = _calculate_adaptive_cooldown(user_id, cooldown_hours)
    
    if adaptive_cooldown > 0:
        last_notification = None
        for notification in reversed(user_notifications):
            if notification.get("reason") == reason:
                last_notification = notification
                break
                
        if last_notification:
            try:
                last_time = datetime.fromisoformat(last_notification.get("timestamp", ""))
                if datetime.now(timezone.utc) - last_time < timedelta(hours=adaptive_cooldown):
                    logger.info(f"bowa_proactive skipped user={user_id} reason={reason} adaptive_cooldown={adaptive_cooldown}h")
                    return True
            except (ValueError, TypeError):
                pass
                
    return False


def is_proactive_duplicate(user_id: str, message: str) -> bool:
    """Check if the exact message has already been sent to the user."""
    adapted_message = adapt_message(message, user_id)
    store = read_notifications_store()
    user_notifications = store.get(user_id, [])
    
    if any(notification.get("message") == adapted_message for notification in user_notifications):
        logger.info(f"bowa_proactive blocked user={user_id} duplicate_message")
        return True
    return False


def save_proactive_message(user_id: str, message: str, reason: str, cooldown_hours: int = 6) -> None:
    """Save a proactive notification after validating cooldowns and duplicates."""
    # 1. Cooldown validation
    if is_proactive_cooldown_active(user_id, reason, cooldown_hours):
        return

    # 2. Duplicate check
    if is_proactive_duplicate(user_id, message):
        return

    adapted_message = adapt_message(message, user_id)
    store = read_notifications_store()
    if user_id not in store:
        store[user_id] = []

    # Save new notification
    notification = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message": adapted_message,
        "reason": reason,
    }

    store[user_id].append(notification)
    # Keep only latest 10
    store[user_id] = store[user_id][-10:]

    write_notifications_store(store)
    emit_event(user_id, "notification", {
        "message": adapted_message,
        "reason": reason,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


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


def _get_ignored_high_urgency_news(user_id: str) -> list[dict[str, Any]]:
    """Get ignored high-urgency news items that need follow-up."""
    history = _get_news_feedback_history(user_id)
    ignored_items = []
    
    for news_id, entry in history.items():
        if (entry.get("action_suggested") == "act" and 
            entry.get("user_action") == "ignored" and
            entry.get("urgency") == "high"):
            ignored_items.append(entry)
    
    return ignored_items


def _get_news_escalation_count(user_id: str) -> int:
    """Get count of previous escalation attempts for news."""
    memory = load_user_memory(user_id) or {}
    return memory.get("news_escalation_count", 0)


def _update_news_escalation_count(user_id: str, increment: bool = True) -> int:
    """Update news escalation count in user memory."""
    memory = load_user_memory(user_id) or {}
    current_count = memory.get("news_escalation_count", 0)
    
    if increment:
        current_count += 1
    else:
        current_count = 0  # Reset when user takes action
    
    memory["news_escalation_count"] = current_count
    save_user_memory(user_id, memory)
    return current_count


def _generate_escalation_message(user_id: str, escalation_count: int, news_item: dict[str, Any]) -> str:
    """Generate escalated message based on ignore count."""
    from services.goal_engine import get_user_goal
    goal = get_user_goal(user_id) or "your goals"

    news_title = news_item.get("title", "high-impact news")
    
    if escalation_count == 1:
        return f"You ignored a high-impact update. This affects your goal: {goal}. Consider reviewing: {news_title[:80]}..."
    elif escalation_count == 2:
        return f"Second reminder: High-urgency news ignored. This directly impacts your progress. Act now or risk falling behind."
    else:
        return f"URGENT: You've repeatedly ignored critical updates. This is harming your {goal} progress. Take action immediately."


def _check_active_hours(user_id: str) -> bool:
    """Check if user is in active hours based on predictor or last_active."""
    try:
        from services.predictor import predict_next_action
        prediction = predict_next_action(user_id)
        if prediction.get("should_act", False):
            return True
    except:
        pass
    
    # Fallback to last_active check
    memory = load_user_memory(user_id) or {}
    last_active_str = memory.get("last_active")
    if not last_active_str:
        return True  # Assume active if no data
    
    try:
        last_active = datetime.fromisoformat(last_active_str)
        hours_since_active = (datetime.now(timezone.utc) - last_active).total_seconds() / 3600
        return hours_since_active <= 12  # Active if within 12 hours
    except (ValueError, TypeError):
        return True


def _get_daily_news_message_count(user_id: str) -> int:
    """Count news-related proactive messages sent today."""
    store = read_notifications_store()
    user_notifications = store.get(user_id, [])
    
    today = datetime.now(timezone.utc).date()
    count = 0
    
    for notification in user_notifications:
        try:
            timestamp = datetime.fromisoformat(notification.get("timestamp", ""))
            if timestamp.date() == today and notification.get("reason") in ["news_escalation", "watch_list_prompt"]:
                count += 1
        except (ValueError, TypeError):
            continue
    
    return count


def _goal_changed_recently(user_id: str) -> bool:
    """Check if user goal changed in last 24 hours."""
    memory = load_user_memory(user_id) or {}
    goal_set_at = memory.get("goal_set_at")
    if not goal_set_at:
        return False
    try:
        set_time = datetime.fromisoformat(goal_set_at)
        return datetime.now(timezone.utc) - set_time < timedelta(hours=24)
    except Exception:
        return False



def _task_completed_today(user_id: str, news_id: str) -> bool:
    """Check if related news task was completed today."""
    history = _get_news_feedback_history(user_id)
    
    for entry in history.values():
        if entry.get("news_id") == news_id and entry.get("follow_through") == True:
            try:
                timestamp = datetime.fromisoformat(entry.get("timestamp", ""))
                if timestamp.date() == datetime.now(timezone.utc).date():
                    return True
            except (ValueError, TypeError):
                continue
    
    return False


def _should_downgrade_tone(user_id: str) -> bool:
    """Check if tone should be downgraded based on consistency."""
    memory = load_user_memory(user_id) or {}
    consistency_score = memory.get("consistency_score", 0.5)
    return consistency_score < 0.3


def _apply_guardrails(user_id: str, news_item: dict[str, Any]) -> tuple[bool, str]:
    """Apply escalation guardrails before sending message."""
    # Check active hours
    if not _check_active_hours(user_id):
        return False, "user_not_active"
    
    # Check daily message limit
    if _get_daily_news_message_count(user_id) >= 2:
        return False, "daily_limit_reached"
    
    # Check if goal changed recently
    if _goal_changed_recently(user_id):
        return False, "goal_changed_recently"
    
    # Check if related task completed today
    news_id = news_item.get("id", "")
    if news_id and _task_completed_today(user_id, news_id):
        return False, "task_completed_today"
    
    return True, "guardrails_passed"


def check_news_escalation(user_id: str) -> None:
    """Check for ignored high-urgency news and escalate if needed."""
    ignored_news = _get_ignored_high_urgency_news(user_id)
    
    if not ignored_news:
        return
    
    escalation_count = _get_news_escalation_count(user_id)
    now = datetime.now(timezone.utc)
    
    # Get the most recent ignored news item
    latest_ignored = max(ignored_news, key=lambda x: x.get("timestamp", ""))
    
    try:
        timestamp = datetime.fromisoformat(latest_ignored.get("timestamp", ""))
        hours_since_ignore = (now - timestamp).total_seconds() / 3600
    except (ValueError, TypeError):
        return
    
    # Escalation timing: 4 hours after ignore, then every 12 hours
    if hours_since_ignore >= 4:
        # Check cooldown (6 hours between escalations)
        user_notifications = get_user_notifications(user_id)
        last_news_notification = None
        
        for notification in reversed(user_notifications):
            if notification.get("reason") == "news_escalation":
                last_news_notification = notification
                break
        
        if last_news_notification:
            try:
                last_time = datetime.fromisoformat(last_news_notification.get("timestamp", ""))
                if now - last_time < timedelta(hours=6):  # Cooldown period
                    return
            except (ValueError, TypeError):
                pass
        
        # Apply guardrails before sending
        guardrails_passed, reason = _apply_guardrails(user_id, latest_ignored)
        if not guardrails_passed:
            logger.info(f"bowa_news_escalation blocked user={user_id} reason={reason}")
            return
        
        # Generate escalated message
        escalation_count = _update_news_escalation_count(user_id, True)
        message = _generate_escalation_message(user_id, escalation_count, latest_ignored)
        
        # Downgrade tone if consistency is low
        if _should_downgrade_tone(user_id):
            message = f"Quick reminder: {latest_ignored.get('title', '')[:80]}... Still relevant?"
        
        save_proactive_message(user_id, message, "news_escalation", cooldown_hours=6)
        logger.info(f"bowa_news_escalation user={user_id} count={escalation_count}")


def trigger_execution_followup(user_id: str) -> None:
    """Trigger follow-up for expired execution session."""
    message = "Time's up! Did you complete the task? Reply 'yes' or 'no'."
    save_proactive_message(user_id, message, "execution_expired")
    logger.info(f"bowa_execution followup user={user_id}")
