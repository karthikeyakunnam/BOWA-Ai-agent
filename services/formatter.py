"""Response formatter for BOWA conversation engine.

Converts structured data from existing BOWA modules into natural,
conversational text. No external AI APIs — pure string formatting.
"""

from typing import Any


def format_roadmap(roadmap_data: dict[str, Any], goal: str) -> str:
    """Format a student roadmap into conversational text."""
    if not roadmap_data:
        return "I couldn't generate a roadmap right now. Tell me your branch again."

    roadmap = roadmap_data.get("roadmap", {})
    branch = roadmap.get("branch_name", "your branch")
    steps = roadmap.get("steps", [])
    weekly = roadmap.get("weekly_actions", [])

    lines = [f"Alright. You're studying {branch} aiming for {goal}."]
    lines.append("Here's how you should approach it:\n")

    for step in steps:
        lines.append(f"  → {step}")

    if weekly:
        lines.append("\nWeekly actions to stay sharp:")
        for action in weekly:
            lines.append(f"  • {action}")

    return "\n".join(lines)


def format_jobs_list(jobs: list[dict[str, Any]], role: str) -> str:
    """Format job listings into conversational text."""
    if not jobs:
        return f"No matching jobs found for '{role}' right now. Try broadening your role."

    top_jobs = jobs[:5]
    lines = [f"Here are roles matching '{role}':\n"]

    for i, job in enumerate(top_jobs, 1):
        company = job.get("company", "Unknown")
        job_role = job.get("role", role)
        location = job.get("location", "Remote")
        lines.append(f"  {i}. {job_role} at {company} — {location}")

    return "\n".join(lines)


def format_skill_gap(
    gap_data: dict[str, Any] | None,
    insights_data: dict[str, Any] | None
) -> str:
    """Format skill gap analysis into conversational text."""
    if not gap_data:
        return ""

    target = gap_data.get("target_role", "your target role")
    matched = gap_data.get("matched_skills", [])
    missing = gap_data.get("missing_skills", [])
    readiness = "0%"
    next_focus = None

    if insights_data:
        readiness = insights_data.get("readiness", "0%")
        next_focus = insights_data.get("next_focus")

    lines = [f"You're aiming for {target}."]

    if matched:
        lines.append(f"Skills you already have: {', '.join(matched)}")

    if missing:
        lines.append(f"Right now, you're missing: {', '.join(missing)}")

    lines.append(f"\nYou're about {readiness} ready.")

    if next_focus:
        lines.append(f"\nNext step: Focus on {next_focus}")

    return "\n".join(lines)


def format_news(news_list: list[dict[str, Any]]) -> str:
    """Format news articles into conversational text."""
    if not news_list:
        return "No major news right now. I'll keep watching."

    # Filter to HIGH and MEDIUM priority first
    important = [
        n for n in news_list
        if n.get("priority") in ("HIGH", "MEDIUM")
    ]

    # Fall back to all news if nothing is high/medium
    display_news = important if important else news_list[:3]

    lines = ["Here's what's happening right now:\n"]

    for article in display_news[:5]:
        title = article.get("title", "Untitled")
        priority = article.get("priority", "LOW")
        category = article.get("category", "General")
        source = article.get("source", "")

        priority_flag = ""
        if priority == "HIGH":
            priority_flag = "🔴 "
        elif priority == "MEDIUM":
            priority_flag = "🟡 "

        source_tag = f" ({source})" if source else ""
        lines.append(f"  {priority_flag}[{category}] {title}{source_tag}")

    return "\n".join(lines)


def format_tracker_confirm(task: str, hours: str) -> str:
    """Format tracker confirmation message."""
    return (
        "Done. I'll track this.\n\n"
        "Today:\n"
        f"  • Task: {task}\n"
        f"  • Time: {hours} hours\n\n"
        "Come back after finishing — I'll evaluate you."
    )


def format_study_with_news(
    roadmap_data: dict[str, Any],
    goal: str,
    news_list: list[dict[str, Any]]
) -> str:
    """Format combined study roadmap + relevant news."""
    roadmap_text = format_roadmap(roadmap_data, goal)

    # Pick one relevant news item if available
    relevant_news = ""
    if news_list:
        top = news_list[0]
        title = top.get("title", "")
        if title:
            relevant_news = (
                f"\n\nAlso, here's something happening in your field right now:\n"
                f"  → {title}"
            )

    return roadmap_text + relevant_news


def format_job_full_response(
    jobs: list[dict[str, Any]],
    role: str,
    gap_data: dict[str, Any] | None,
    insights_data: dict[str, Any] | None
) -> str:
    """Format complete job response: listings + skill gap + next steps."""
    parts = []

    gap_text = format_skill_gap(gap_data, insights_data)
    if gap_text:
        parts.append(gap_text)

    jobs_text = format_jobs_list(jobs, role)
    parts.append(jobs_text)

    # Add action prompt
    readiness = "0"
    if insights_data:
        readiness = insights_data.get("readiness", "0%").replace("%", "")

    try:
        readiness_int = int(readiness)
    except ValueError:
        readiness_int = 0

    if readiness_int >= 70:
        parts.append("\nYou're in good shape. Start applying this week.")
    else:
        parts.append("\nDo you want me to create a 7-day plan for this?")

    return "\n\n".join(parts)
