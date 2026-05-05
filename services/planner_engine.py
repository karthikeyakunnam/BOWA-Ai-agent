"""Multi-Step Planning Engine for BOWA.

Generates structured plans for complex goals and tracks progress.
"""

from typing import Any, Dict, List


def _is_large_goal(intent: str, message: str) -> bool:
    """Determine if the user's goal requires multi-step planning."""
    large_keywords = [
        "career", "study", "learn", "build", "create", "transform",
        "become", "master", "complete", "achieve", "goal", "plan"
    ]
    message_lower = message.lower()
    return (
        intent in ["study", "jobs", "tracker"] or
        any(keyword in message_lower for keyword in large_keywords) or
        len(message.split()) > 5  # Complex requests
    )


def _generate_steps_for_goal(intent: str, message: str) -> List[Dict[str, Any]]:
    """Generate specific steps based on intent and message."""
    if intent == "study":
        return [
            {"step": 1, "action": "Research fundamentals"},
            {"step": 2, "action": "Set up learning environment"},
            {"step": 3, "action": "Complete first module"},
            {"step": 4, "action": "Practice and apply"},
            {"step": 5, "action": "Build a small project"}
        ]
    elif intent == "jobs":
        return [
            {"step": 1, "action": "Update resume and portfolio"},
            {"step": 2, "action": "Research target companies"},
            {"step": 3, "action": "Apply to 5 positions"},
            {"step": 4, "action": "Prepare for interviews"},
            {"step": 5, "action": "Follow up and negotiate"}
        ]
    elif "sql" in message.lower():
        return [
            {"step": 1, "action": "Learn SQL basics (SELECT, FROM, WHERE)"},
            {"step": 2, "action": "Practice with sample databases"},
            {"step": 3, "action": "Master JOINs and aggregations"},
            {"step": 4, "action": "Build a data analysis query"},
            {"step": 5, "action": "Create a SQL project"}
        ]
    else:
        # Generic plan for large goals
        return [
            {"step": 1, "action": "Define clear objectives"},
            {"step": 2, "action": "Break down into actionable tasks"},
            {"step": 3, "action": "Set up resources and tools"},
            {"step": 4, "action": "Execute first phase"},
            {"step": 5, "action": "Review progress and adjust"}
        ]


def generate_plan(state: Dict[str, Any], intent: str, message: str) -> Dict[str, Any] | None:
    """Generate a multi-step plan if appropriate, otherwise return None."""
    # Skip if already in execution
    if state.get("trajectory", {}).get("current_stage") == "executing":
        return None

    # Skip if user is confused (plan clarification instead)
    if state.get("mood") == "confused":
        return None

    # Skip if already has an active plan
    if state.get("active_plan"):
        return None

    # Generate plan for large goals
    if _is_large_goal(intent, message):
        steps = _generate_steps_for_goal(intent, message)
        return {
            "steps": steps,
            "current_step": 1,
            "total_steps": len(steps)
        }

    return None