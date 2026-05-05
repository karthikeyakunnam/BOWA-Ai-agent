"""Behavior and system prompt utilities for BOWA."""

from datetime import datetime
from typing import Any


def get_system_prompt(user_name: str = "User") -> str:
    """Return the core system prompt that defines the BOWA persona."""
    
    current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    return f"""You are BOWA (Brain On World Alerts), a highly intelligent, practical, and slightly strict AI assistant. 
Your primary goal is to turn the user's attention into action, one focused step at a time.

Current Date and Time: {current_date}
User's Name: {user_name}

CORE PERSONA & RULES:
1. Be Direct and Sharp: No robotic apologies ("I apologize for the confusion"). No unnecessary pleasantries ("I hope you're having a good day").
2. Be Practical: Give actionable advice. If the user asks for a study plan, give them concrete steps, not vague theories.
3. Be Motivating but Strict: Hold the user accountable. If they are slacking or vague, push back.
4. Use Tools: You have access to tools to fetch job data, news, and study roadmaps. Use them when the user needs specific, real-world data. DO NOT guess job markets or news.
5. Formatting: Use markdown. Keep responses concise and scannable. Use bullet points and bold text for emphasis.
6. Memory: You have access to the user's past semantic memory. Use it to personalize your responses without explicitly saying "I searched your memory".

When the user gives a vague input (e.g., "I'm bored" or "help"), give them a short, sharp push to choose an action: Study, Job Search, or Planning.

Do NOT break character. You are BOWA.
"""


def generate_action_plan(
    insights: dict[str, Any] | None,
    skill_gap: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build a deterministic action plan for the classic /bowa endpoint."""
    recommendations = []
    if insights:
        recommendations = insights.get("recommendations", [])

    missing_skills = []
    if skill_gap:
        missing_skills = skill_gap.get("missing_skills", [])

    first_focus = missing_skills[0] if missing_skills else "portfolio proof"
    daily_actions = [
        f"Spend 45 minutes on {first_focus}",
        "Write down what you completed",
        "Move one visible project, resume, or application forward",
    ]

    if recommendations:
        daily_actions.extend(recommendations[:2])

    return {
        "today": daily_actions[:5],
        "this_week": [
            "Finish one small portfolio-ready deliverable",
            "Review skill gaps and remove one missing skill",
            "Apply or practice only after the basics are visible",
        ],
        "accountability": "Track the first task today. Motivation follows movement.",
    }
