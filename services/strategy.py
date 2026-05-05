"""Adaptive Strategy Engine for BOWA.

Decides the best interaction strategy based on user state, reflection, and intent.
"""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def choose_strategy(state: Dict[str, Any], reflection: Dict[str, Any], intent: str) -> Dict[str, Any]:
    """Choose the best strategy for the next action."""
    trajectory = state.get("trajectory", {})
    consistency_score = trajectory.get("consistency_score", 0.5)
    mood = state.get("mood", "neutral")
    
    adjustment = reflection.get("adjustment", "continue")
    
    # Rules:
    # struggling → simplify
    # inconsistent → push
    # disciplined → challenge
    # confused → support

    if mood == "confused" or adjustment == "change_strategy":
        strategy = "support"
        reason = "User is confused and needs support."
    elif adjustment == "reduce_difficulty" or mood == "lazy":
        strategy = "simplify"
        reason = "User is struggling and needs a simpler approach."
    elif consistency_score > 0.7 and adjustment == "increase_challenge":
        strategy = "challenge"
        reason = "User is disciplined and ready for a challenge."
    elif consistency_score < 0.5:
        strategy = "push"
        reason = "User is inconsistent and needs a push."
    else:
        strategy = "push" # Default BOWA strategy
        reason = "Standard interaction flow."

    logger.info("bowa_strategy type=%s", strategy)

    return {
        "strategy": strategy,
        "reason": reason
    }
