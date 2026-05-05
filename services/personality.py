"""Humanization and Adaptive Personality Engine for BOWA."""

import logging
from typing import Any

from services.memory import load_user_memory

logger = logging.getLogger(__name__)


def detect_user_type(user_id: str) -> str:
    """Detect user personality type based on their data."""
    memory = load_user_memory(user_id) or {}

    consistency_score = memory.get("consistency_score", 0.5)
    prev_consistency = memory.get("prev_consistency_score", consistency_score)
    interaction_count = memory.get("interaction_count", 0)

    if interaction_count < 5:
        return "new"

    if consistency_score < 0.3:
        return "struggling"

    if consistency_score < prev_consistency:
        return "inconsistent"

    if consistency_score > 0.7:
        return "disciplined"

    return "neutral"


def get_personality_tone(user_type: str) -> str:
    """Map user type to personality tone."""
    tone_map = {
        "struggling": "supportive",
        "inconsistent": "firm",
        "disciplined": "respectful",
        "new": "clear",
        "neutral": "neutral"
    }
    return tone_map.get(user_type, "neutral")


def adapt_tone(message: str, user_type: str, tone: str) -> str:
    """Adapt message tone based on user personality."""
    # Base adaptations
    if tone == "supportive":
        # Add empathy and encouragement
        if "start" in message.lower() or "do" in message.lower():
            message = message.replace("Start", "I know it's tough, but let's start")
            message = message.replace("Do", "Try to do")
        if "!" in message:
            message = message.replace("!", ". I believe in you.")

    elif tone == "firm":
        # Add directness and correction
        if "slipping" in message.lower() or "dropping" in message.lower():
            message += " This needs to change today."
        if "waiting" in message.lower():
            message = message.replace("Stop waiting", "No more waiting")

    elif tone == "respectful":
        # Add respect and challenge
        if "good" in message.lower() or "well" in message.lower():
            message = message.replace("Good", "Impressive")
        if "increase" in message.lower():
            message += " You can handle it."

    elif tone == "clear":
        # Keep simple and direct
        # Remove complex words, keep straightforward
        pass

    # Avoid repetition by varying slightly based on user_type
    if user_type == "struggling":
        message = message.replace("now", "when you're ready")
    elif user_type == "inconsistent":
        message = message.replace("today", "right now")

    return message


def adapt_message(message: str, user_id: str) -> str:
    """Adapt a message for the user's personality."""
    user_type = detect_user_type(user_id)
    tone = get_personality_tone(user_type)
    adapted = adapt_tone(message, user_type, tone)

    logger.info(f"bowa_personality user={user_id} type={user_type} tone={tone} original='{message}' adapted='{adapted}'")
    return adapted