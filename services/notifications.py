"""Console notification engine for BOWA."""

from typing import Any


def parse_readiness(readiness: str | int | float | None) -> int:
    """Convert readiness values like '40%' into an integer."""
    if readiness is None:
        return 0

    if isinstance(readiness, int | float):
        return round(readiness)

    cleaned_value = readiness.replace("%", "").strip()

    try:
        return round(float(cleaned_value))
    except ValueError:
        return 0


def get_readiness(data: dict[str, Any]) -> int:
    """Extract readiness from a BOWA response."""
    insights = data.get("insights") or {}
    return parse_readiness(insights.get("readiness"))


def get_next_focus(data: dict[str, Any]) -> str | None:
    """Extract next focus from a BOWA response."""
    insights = data.get("insights") or {}
    return insights.get("next_focus")


def get_missing_skills(data: dict[str, Any]) -> set[str]:
    """Extract missing skills from a BOWA response."""
    skill_gap = data.get("skill_gap") or {}
    missing_skills = skill_gap.get("missing_skills") or []
    return {
        skill
        for skill in missing_skills
        if isinstance(skill, str) and skill.strip()
    }


def get_high_priority_news_keys(data: dict[str, Any]) -> set[str]:
    """Extract identifiers for HIGH priority news articles."""
    news_items = data.get("news") or []
    high_priority_news = set()

    for article in news_items:
        if not isinstance(article, dict):
            continue
        if article.get("priority") != "HIGH":
            continue

        news_key = article.get("url") or article.get("title")
        if news_key:
            high_priority_news.add(news_key)

    return high_priority_news


def get_job_keys(data: dict[str, Any]) -> set[str]:
    """Extract stable identifiers for job recommendations."""
    jobs = data.get("jobs") or []
    job_keys = set()

    for job in jobs:
        if not isinstance(job, dict):
            continue

        company = job.get("company", "")
        role = job.get("role", "")
        url = job.get("url", "")
        job_key = f"{company}|{role}|{url}"

        if job_key.strip("|"):
            job_keys.add(job_key)

    return job_keys


def generate_notification_message(
    notification_type: str,
    context: dict[str, Any]
) -> str:
    """Generate a human-readable notification message."""
    if notification_type == "skill_update":
        readiness = context.get("readiness", 0)
        next_focus = context.get("next_focus")

        if next_focus:
            return (
                f"Your readiness improved to {readiness}%. "
                f"Focus on {next_focus} next."
            )

        return f"Your readiness improved to {readiness}%."

    if notification_type == "new_missing_skill":
        skill = context.get("skill", "a new skill")
        return f"New missing skill detected: {skill}. Add it to your plan."

    if notification_type == "news_alert":
        title = context.get("title", "High priority news")
        return f"High priority news detected: {title}"

    if notification_type == "job_alert":
        role = context.get("role", "a new role")
        company = context.get("company", "a company")
        return f"New job recommendation added: {role} at {company}"

    return "Important BOWA update detected."


def build_notification(
    user_id: str,
    notification_type: str,
    context: dict[str, Any]
) -> dict[str, str]:
    """Build a notification payload."""
    return {
        "user_id": user_id,
        "message": generate_notification_message(notification_type, context),
        "type": notification_type
    }


def get_new_high_priority_news(
    old_data: dict[str, Any],
    new_data: dict[str, Any]
) -> list[dict[str, Any]]:
    """Return HIGH priority news articles that were not present before."""
    old_news_keys = get_high_priority_news_keys(old_data)
    new_articles = []

    for article in new_data.get("news") or []:
        if not isinstance(article, dict):
            continue
        if article.get("priority") != "HIGH":
            continue

        news_key = article.get("url") or article.get("title")
        if news_key and news_key not in old_news_keys:
            new_articles.append(article)

    return new_articles


def get_new_jobs(
    old_data: dict[str, Any],
    new_data: dict[str, Any]
) -> list[dict[str, Any]]:
    """Return job recommendations that were not present before."""
    old_job_keys = get_job_keys(old_data)
    new_jobs = []

    for job in new_data.get("jobs") or []:
        if not isinstance(job, dict):
            continue

        company = job.get("company", "")
        role = job.get("role", "")
        url = job.get("url", "")
        job_key = f"{company}|{role}|{url}"

        if job_key.strip("|") and job_key not in old_job_keys:
            new_jobs.append(job)

    return new_jobs


def check_for_updates(
    old_data: dict[str, Any] | None,
    new_data: dict[str, Any]
) -> list[dict[str, str]]:
    """Compare previous and current BOWA output and return notifications."""
    if not old_data:
        return []

    user_id = new_data.get("user_id") or "unknown"
    notifications = []

    old_readiness = get_readiness(old_data)
    new_readiness = get_readiness(new_data)
    readiness_delta = new_readiness - old_readiness

    if readiness_delta >= 10:
        notifications.append(build_notification(
            user_id,
            "skill_update",
            {
                "readiness": new_readiness,
                "next_focus": get_next_focus(new_data)
            }
        ))

    old_missing_skills = get_missing_skills(old_data)
    new_missing_skills = get_missing_skills(new_data)
    for skill in sorted(new_missing_skills - old_missing_skills):
        notifications.append(build_notification(
            user_id,
            "new_missing_skill",
            {"skill": skill}
        ))

    for article in get_new_high_priority_news(old_data, new_data):
        notifications.append(build_notification(
            user_id,
            "news_alert",
            {"title": article.get("title")}
        ))

    for job in get_new_jobs(old_data, new_data):
        notifications.append(build_notification(
            user_id,
            "job_alert",
            {
                "company": job.get("company"),
                "role": job.get("role")
            }
        ))

    return notifications
