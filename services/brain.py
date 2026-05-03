"""Unified Decision Engine for BOWA.

The brain layer orchestrates existing services. It does not use AI APIs; it
routes input to the right local modules and returns a combined response.
"""

from typing import Any

from services.behavior import generate_action_plan
from services.insights import generate_insights
from services.jobs import fetch_jobs, filter_jobs, get_skill_gap_analysis
from services.memory import load_user_memory, update_user_memory
from services.news import get_priority_news
from services.student import get_student_roadmap


def normalize_user_type(user_type: str) -> str:
    """Normalize incoming user type values."""
    normalized = user_type.strip().lower().replace("-", "_").replace(" ", "_")

    aliases = {
        "student": "student",
        "job": "job_seeker",
        "jobs": "job_seeker",
        "jobseeker": "job_seeker",
        "job_seeker": "job_seeker",
        "professional": "professional",
        "working_professional": "professional"
    }

    return aliases.get(normalized, normalized)


def get_target_role(input_data: dict[str, Any]) -> str:
    """Read target role from goal or role input."""
    return (input_data.get("goal") or input_data.get("role") or "").strip()


def get_user_skills(input_data: dict[str, Any]) -> list[str]:
    """Return cleaned user skills from request data."""
    skills = input_data.get("skills") or []

    if isinstance(skills, str):
        skills = skills.split(",")

    return [
        skill.strip()
        for skill in skills
        if isinstance(skill, str) and skill.strip()
    ]


def merge_request_with_memory(input_data: dict[str, Any]) -> dict[str, Any]:
    """Merge stored user memory with the incoming request."""
    user_id = input_data.get("user_id")
    previous_data = load_user_memory(user_id)
    merged_data = previous_data.copy()

    for key, value in input_data.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, list) and not value:
            continue
        merged_data[key] = value

    return merged_data


def build_empty_response(
    user_id: str | None,
    user_type: str,
    effective_input: dict[str, Any]
) -> dict[str, Any]:
    """Create the standard brain response shape."""
    return {
        "user_id": user_id,
        "user_type": user_type,
        "effective_input": effective_input,
        "roadmap": None,
        "jobs": [],
        "skill_gap": None,
        "insights": None,
        "action_plan": None,
        "news": []
    }


def attach_insights_and_action_plan(
    response: dict[str, Any],
    effective_input: dict[str, Any]
) -> None:
    """Add insights and behavior plan to the brain response."""
    response["insights"] = generate_insights(
        effective_input,
        response["skill_gap"]
    )
    response["action_plan"] = generate_action_plan(
        response["insights"],
        response["skill_gap"]
    )


def process_user_request(input_data: dict[str, Any]) -> dict[str, Any]:
    """Process one unified BOWA request across roadmap, jobs, and news."""
    user_id = input_data.get("user_id")
    effective_input = merge_request_with_memory(input_data)
    user_type = normalize_user_type(effective_input.get("user_type", ""))
    target_role = get_target_role(effective_input)
    user_skills = get_user_skills(effective_input)
    response = build_empty_response(user_id, user_type, effective_input)

    if user_type == "student":
        branch = (effective_input.get("branch") or "Other").strip()
        response["roadmap"] = get_student_roadmap(branch)

        if target_role:
            jobs = fetch_jobs()
            response["jobs"] = filter_jobs(jobs, target_role)
            response["skill_gap"] = get_skill_gap_analysis(target_role, user_skills)
            attach_insights_and_action_plan(response, effective_input)

    elif user_type == "job_seeker":
        if target_role:
            jobs = fetch_jobs()
            response["jobs"] = filter_jobs(jobs, target_role)
            response["skill_gap"] = get_skill_gap_analysis(target_role, user_skills)
            attach_insights_and_action_plan(response, effective_input)

    response["news"] = get_priority_news()
    if user_id:
        response["memory"] = update_user_memory(user_id, effective_input)
    else:
        response["memory"] = None

    return response
