"""Dynamic Action Selection Layer for BOWA.

Decides the next adaptive action based on user state, intent, and context.
"""

from typing import Any, Dict


def decide_next_action(
    state: Dict[str, Any],
    intent: str,
    structured_data: Dict[str, Any]
) -> str:
    """Decide the next action based on user state and context."""
    consistency = state.get("consistency_score", 0.5)
    mood = state.get("mood", "neutral")
    trajectory = state.get("trajectory", {})
    current_stage = trajectory.get("current_stage", "unclear")
    user_message = structured_data.get("user_message", "").lower().strip()
    tone = structured_data.get("tone", "firm")

    # Rule 1: If user is in execution and says vague input → continue
    if current_stage == "executing" and intent == "general" and user_message in ["hmm", "idk", "what", ""]:
        return "continue"

    # Rule 2: If user says "jobs" → switch_to_jobs
    if "job" in user_message or intent == "jobs":
        return "switch_to_jobs"

    # Rule 3: If user confused → simplify
    if mood == "confused" or tone == "explanatory":
        return "simplify"

    # Rule 4: If user lazy → motivate
    if mood == "lazy" or consistency < 0.3:
        return "motivate"

    # Rule 5: If consistency dropping → push
    if trajectory.get("feedback") == "dropping" or consistency < 0.5:
        return "push"

    # Rule 6: If user changes topic → switch context
    if intent in ["study", "tracker", "news"] and current_stage not in ["planning", "executing"]:
        return f"switch_to_{intent}"

    # Rule 7: If no clear direction → ask clarification
    if intent == "general" and not user_message:
        return "ask_clarification"

    # Default: continue
    return "continue"