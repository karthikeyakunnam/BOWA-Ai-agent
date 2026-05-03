"""Insight and recommendation engine for BOWA."""

from typing import Any


def calculate_readiness(skill_gap_data: dict[str, Any] | None) -> int:
    """Estimate readiness from matched and required skills."""
    if not skill_gap_data:
        return 0

    required_skills = skill_gap_data.get("required_skills", [])
    matched_skills = skill_gap_data.get("matched_skills", [])

    if not required_skills:
        return 0

    readiness = (len(matched_skills) / len(required_skills)) * 100
    return round(readiness)


def get_next_focus(skill_gap_data: dict[str, Any] | None) -> str | None:
    """Return the next missing skill to focus on."""
    if not skill_gap_data:
        return None

    missing_skills = skill_gap_data.get("missing_skills", [])
    if missing_skills:
        return missing_skills[0]

    return None


def build_recommendations(
    user_data: dict[str, Any],
    skill_gap_data: dict[str, Any] | None,
    readiness: int,
    next_focus: str | None
) -> list[str]:
    """Generate deterministic recommendations from user and skill data."""
    goal = user_data.get("goal") or user_data.get("role") or "your target role"

    if not skill_gap_data:
        return [
            "Set a clear goal",
            "Add your current skills",
            "Review roadmap and news updates"
        ]

    if next_focus:
        recommendations = [
            f"Learn {next_focus} basics",
            "Build one project using your target role skills",
            "Practice real datasets or real-world tasks"
        ]
    else:
        recommendations = [
            f"Build a portfolio project for {goal}",
            "Practice interview questions",
            "Apply for jobs if >70% ready"
        ]

    if readiness >= 70:
        recommendations.append("Apply for jobs if >70% ready")
    else:
        recommendations.append("Focus on next missing skill")

    return recommendations


def generate_insights(
    user_data: dict[str, Any],
    skill_gap_data: dict[str, Any] | None
) -> dict[str, Any]:
    """Generate actionable insight output for BOWA."""
    readiness = calculate_readiness(skill_gap_data)
    next_focus = get_next_focus(skill_gap_data)
    recommendations = build_recommendations(
        user_data,
        skill_gap_data,
        readiness,
        next_focus
    )

    return {
        "readiness": f"{readiness}%",
        "next_focus": next_focus,
        "recommendations": recommendations
    }
