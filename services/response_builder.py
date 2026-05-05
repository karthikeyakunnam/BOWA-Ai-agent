"""Response Composition Layer for BOWA.

Builds structured response data from state, intent, and action output
before passing to LLM for natural language conversion.
"""

from typing import Any, Dict


def _determine_tone(state: Dict[str, Any], intent: str) -> str:
    """Determine response tone based on user state and intent."""
    consistency = state.get("consistency_score", 0.5)
    mood = state.get("mood", "neutral")
    trajectory = state.get("trajectory", {})
    current_stage = trajectory.get("current_stage", "unclear")

    # Tone logic
    if consistency < 0.3 or mood == "confused":
        return "supportive"
    elif consistency > 0.7 and current_stage in ["consistent", "advanced"]:
        return "challenging"
    elif mood == "lazy" or trajectory.get("feedback") == "dropping":
        return "firm"
    else:
        return "firm"


def _determine_pressure(state: Dict[str, Any], intent: str) -> bool:
    """Determine if response should apply pressure for action."""
    consistency = state.get("consistency_score", 0.5)
    mood = state.get("mood", "neutral")

    # Apply pressure if user is lazy, inconsistent, or needs motivation
    return consistency < 0.5 or mood == "lazy" or intent in ["general", "tracker"]


def _extract_next_step(action_output: str) -> str:
    """Extract or infer the next concrete step from action output."""
    lines = action_output.splitlines()
    for line in lines:
        if "next:" in line.lower() or "do" in line.lower() and "now" in line.lower():
            return line.strip()
    # Fallback to last line if it looks like an action
    if lines and any(word in lines[-1].lower() for word in ["start", "do", "begin", "next"]):
        return lines[-1].strip()
    return "Continue with your current plan."


def build_response(
    state: Dict[str, Any],
    intent: str,
    action_output: str,
    strategy: Dict[str, Any] = None,
    reflection: Dict[str, Any] = None
) -> Dict[str, Any]:
    """Build structured response data for LLM processing."""
    trajectory = state.get("trajectory", {})
    consistency = trajectory.get("consistency_score", 0.5)
    mood = state.get("mood", "neutral")

    plan = state.get("active_plan")
    plan_step = plan.get("current_step") if plan else None
    remaining_steps = plan.get("total_steps") - plan_step + 1 if plan and plan_step else None

    return {
        "stage": trajectory.get("current_stage", "unclear"),
        "intent": intent,
        "tone": _determine_tone(state, intent),
        "user_condition": {
            "consistency": consistency,
            "mood": mood,
        },
        "message": action_output.strip(),
        "next_step": _extract_next_step(action_output),
        "pressure": _determine_pressure(state, intent),
        "plan_step": plan_step,
        "remaining_steps": remaining_steps,
        "strategy": strategy,
        "reflection": reflection,
    }