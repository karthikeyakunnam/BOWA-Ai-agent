"""Behavior and action plan engine for BOWA."""

from typing import Any


def get_focus_skill(
    insights: dict[str, Any] | None,
    skill_gap: dict[str, Any] | None
) -> str:
    """Choose the skill that should drive the action plan."""
    if insights and insights.get("next_focus"):
        return insights["next_focus"]

    if skill_gap:
        missing_skills = skill_gap.get("missing_skills", [])
        if missing_skills:
            return missing_skills[0]

    return "your target skill"


def generate_action_plan(
    insights: dict[str, Any] | None,
    skill_gap: dict[str, Any] | None
) -> dict[str, Any]:
    """Generate a structured 5-day behavior plan."""
    focus_skill = get_focus_skill(insights, skill_gap)

    return {
        "plan_type": "5_day_plan",
        "days": [
            {
                "day": 1,
                "task": f"Learn basics of {focus_skill}"
            },
            {
                "day": 2,
                "task": f"Practice {focus_skill} exercises"
            },
            {
                "day": 3,
                "task": f"Build a mini project using {focus_skill}"
            },
            {
                "day": 4,
                "task": f"Revise {focus_skill} concepts and improve your project"
            },
            {
                "day": 5,
                "task": f"Apply {focus_skill} in a mock task, interview, or real task"
            }
        ]
    }
