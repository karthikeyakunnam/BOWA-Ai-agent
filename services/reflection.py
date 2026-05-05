"""Reflection Engine for BOWA.

Evaluates if the previous action worked and suggests adjustments.
"""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def analyze_performance(state: Dict[str, Any], last_action: str, result: str) -> Dict[str, Any]:
    """Evaluate if the previous action worked based on the current context."""
    # Analyze trajectory and consistency
    trajectory = state.get("trajectory", {})
    consistency_score = trajectory.get("consistency_score", 0.5)
    mood = state.get("mood", "neutral")
    
    # Simple heuristic to determine success based on result intent/content
    # Here `result` could be the user's latest message indicating follow-up
    lowered_result = result.lower().strip()
    
    success = False
    if "yes" in lowered_result or "done" in lowered_result or "completed" in lowered_result or "next" in lowered_result:
        success = True

    # Check failure conditions
    fails_repeatedly = trajectory.get("feedback") == "dropping" or consistency_score < 0.3
    stuck = mood == "confused" or "what" in lowered_result or "help" in lowered_result

    # Determine adjustment
    if fails_repeatedly:
        adjustment = "reduce_difficulty"
        reason = "User is failing repeatedly."
    elif stuck:
        adjustment = "change_strategy"
        reason = "User is stuck or confused."
    elif success:
        adjustment = "increase_challenge"
        reason = "User succeeded."
    else:
        adjustment = "continue"
        reason = "User is progressing normally."

    reflection_data = {
        "success": success,
        "reason": reason,
        "adjustment": adjustment
    }

    logger.info("bowa_reflection result=%s adjustment=%s", success, adjustment)
    
    return reflection_data
