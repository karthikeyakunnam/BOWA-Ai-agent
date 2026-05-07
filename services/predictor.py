"""Prediction & Anticipation Engine for BOWA - predict and act proactively."""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from services.execution import start_execution_session
from services.memory import load_user_memory
from services.personality import adapt_message
from services.proactive import save_proactive_message
from services.news_feedback import get_effective_impact_score

logger = logging.getLogger(__name__)


def analyze_user_patterns(user_id: str) -> dict[str, Any]:
    """Analyze user memory to extract patterns."""
    memory = load_user_memory(user_id) or {}

    # Extract patterns from memory
    active_hours = memory.get("active_hours", [])  # list of hour ints
    study_frequency = memory.get("study_frequency", 0)  # sessions per day
    completion_rate = memory.get("completion_rate", 0.5)  # 0-1
    hesitation_patterns = memory.get("hesitation_patterns", [])  # list of behaviors
    last_active = memory.get("last_active")
    consistency_score = memory.get("consistency_score", 0.5)
    prev_consistency = memory.get("prev_consistency_score", consistency_score)

    return {
        "active_hours": active_hours,
        "study_frequency": study_frequency,
        "completion_rate": completion_rate,
        "hesitation_patterns": hesitation_patterns,
        "last_active": last_active,
        "consistency_score": consistency_score,
        "prev_consistency": prev_consistency,
    }


def predict_next_action(user_id: str) -> dict[str, Any]:
    """Predict if BOWA should act proactively."""
    patterns = analyze_user_patterns(user_id)
    now = datetime.now(timezone.utc)
    current_hour = now.hour

    # Rule 1: User always active at same time
    if current_hour in patterns["active_hours"] and patterns["study_frequency"] > 0:
        last_active = patterns.get("last_active")
        if last_active:
            last_active_dt = datetime.fromisoformat(last_active)
            if now - last_active_dt > timedelta(hours=1):  # not active recently
                return {
                    "should_act": True,
                    "reason": "usual_active_time",
                    "suggested_action": "start_session",
                    "message": "You always start around now. Begin your session."
                }

    # Rule 2: Consistency dropping
    if patterns["consistency_score"] < patterns["prev_consistency"] and patterns["consistency_score"] < 0.7:
        return {
            "should_act": True,
            "reason": "consistency_dropping",
            "suggested_action": "escalate",
            "message": "Your consistency is dropping. Fix it now before it worsens."
        }

    # Rule 3: Repeated failure
    if patterns["completion_rate"] < 0.3 and "repeated_failure" in patterns["hesitation_patterns"]:
        return {
            "should_act": True,
            "reason": "repeated_failure",
            "suggested_action": "reduce_difficulty",
            "message": "You've been struggling. Let's break it down - start with 10 minutes."
        }

    # Rule 4: High consistency
    if patterns["consistency_score"] > 0.8 and patterns["prev_consistency"] > 0.8:
        return {
            "should_act": True,
            "reason": "high_consistency",
            "suggested_action": "increase_difficulty",
            "message": "You're on a roll! Increase the challenge - aim for 45 minutes."
        }

    return {"should_act": False, "reason": "no_pattern", "suggested_action": None, "message": None}


def recompute_confidence_with_decay(user_id: str) -> float:
    """Recompute confidence score using effective impact with time decay."""
    memory = load_user_memory(user_id) or {}
    
    # Get effective impact score with time decay
    effective_impact = get_effective_impact_score(user_id)
    
    # Get current confidence
    current_confidence = memory.get("confidence_score", 50)
    
    # Blend effective impact with current confidence
    # Weight effective impact more for recent activity
    updated_confidence = (current_confidence * 0.6) + (effective_impact * 0.4)
    
    # Normalize to 0-100 range
    updated_confidence = min(max(updated_confidence, 0), 100)
    
    # Update memory
    memory["confidence_score"] = updated_confidence
    save_user_memory(user_id, memory)
    
    return updated_confidence


def execute_prediction(user_id: str, prediction: dict[str, Any]) -> None:
    """Execute the predicted action."""
    action = prediction["suggested_action"]
    message = prediction["message"]
    reason = prediction["reason"]

    if action == "start_session":
        task = "Predicted session based on your patterns"
        start_execution_session(user_id, task, duration=25)
        save_proactive_message(user_id, message, reason)
    elif action in ["escalate", "reduce_difficulty", "increase_difficulty"]:
        save_proactive_message(user_id, message, reason)

    logger.info(f"bowa_predict user={user_id} action={action} reason={reason}")