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
            {"action": "Research fundamentals"},
            {"action": "Set up learning environment"},
            {"action": "Complete first module"},
            {"action": "Practice and apply"},
            {"action": "Build a small project"}
        ]
    elif intent == "jobs":
        return [
            {"action": "Update resume and portfolio"},
            {"action": "Research target companies"},
            {"action": "Apply to 5 positions"},
            {"action": "Prepare for interviews"},
            {"action": "Follow up and negotiate"}
        ]
    elif "sql" in message.lower():
        return [
            {"action": "Learn SQL basics (SELECT, FROM, WHERE)"},
            {"action": "Practice with sample databases"},
            {"action": "Master JOINs and aggregations"},
            {"action": "Build a data analysis query"},
            {"action": "Create a SQL project"}
        ]
    else:
        # Generic plan for large goals
        return [
            {"action": "Define clear objectives"},
            {"action": "Break down into actionable tasks"},
            {"action": "Set up resources and tools"},
            {"action": "Execute first phase"},
            {"action": "Review progress and adjust"}
        ]


def _normalize_plan_steps(steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "step": index + 1,
            "action": str(step.get("action", "Stay focused")) if isinstance(step, dict) else str(step),
            "done": False,
        }
        for index, step in enumerate(steps)
    ]


def generate_plan(state: Dict[str, Any], intent: str, message: str) -> Dict[str, Any] | None:
    """Generate a multi-step plan if appropriate, otherwise return None."""
    # Skip if already in execution
    if state.get("trajectory", {}).get("current_stage") == "executing":
        return None

    # Skip if user is confused (plan clarification instead)
    if state.get("mood") == "confused":
        return None

    # Skip if already has an active plan that is not completed
    active_plan = state.get("active_plan")
    if isinstance(active_plan, dict) and not active_plan.get("completed"):
        return None

    # Generate plan for large goals
    if _is_large_goal(intent, message):
        steps = _generate_steps_for_goal(intent, message)
        normalized = _normalize_plan_steps(steps)
        return {
            "goal": message or "Your goal",
            "steps": normalized,
            "current_step": 1,
            "total_steps": len(normalized),
            "completed": False,
        }

    return None