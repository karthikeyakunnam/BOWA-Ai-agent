"""Daily summary generator for BOWA.

Creates end-of-day intelligence summaries with insights and recommendations.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from services.memory import load_user_memory, save_user_memory
from services.streak import get_user_streak
from services.trajectory import load_trajectory
from services.news_service import get_priority_news

logger = logging.getLogger(__name__)


def _extract_key_takeaways(news_data: list[dict[str, Any]], goal: str) -> list[str]:
    """Extract key insights from today's news."""
    takeaways = []
    
    if not news_data:
        return ["No major industry updates today"]
    
    # Analyze high-urgency and high-relevance news
    high_relevance = [n for n in news_data if n.get("relevance_score", 0) >= 70]
    
    for news in high_relevance[:2]:
        category = news.get("category", "General")
        title = news.get("title", "")
        
        if category == "AI":
            takeaways.append(f"AI sector: {title[:50]}...")
        elif category == "Jobs":
            takeaways.append(f"Job market: {title[:50]}...")
        elif category == "Finance":
            takeaways.append(f"Economy: {title[:50]}...")
        else:
            takeaways.append(f"Industry update: {title[:50]}...")
    
    if not takeaways:
        takeaways.append("Market activity within your sector")
    
    return takeaways[:3]


def _calculate_impact_for_user(news_data: list[dict[str, Any]], goal: str, trajectory: dict[str, Any]) -> list[str]:
    """Calculate impact of today's events on user's specific goal."""
    impacts = []
    
    if not goal:
        return ["Set a goal to receive personalized impact analysis"]
    
    goal_lower = goal.lower()
    trajectory_stage = trajectory.get("current_stage", "Planning").lower()
    
    # Analyze relevant news
    for news in news_data:
        if news.get("relevance_score", 0) < 60:
            continue
            
        category = news.get("category", "").lower()
        priority = news.get("priority", "").lower()
        
        if "ai" in goal_lower and category == "ai":
            if priority == "high":
                impacts.append("Major AI advancement - increases demand for your skillset")
            else:
                impacts.append("New AI tools becoming available - consider learning next")
        
        if "job" in goal_lower and category == "jobs":
            if priority == "high":
                impacts.append("Job market shift - adapt your strategy for upcoming searches")
            else:
                impacts.append("Job trends shifting - monitor for opportunities")
        
        if "data" in goal_lower and category in ["ai", "finance"]:
            impacts.append(f"Data skills in high demand - {category} sector is moving")
    
    if not impacts:
        if trajectory_stage == "execution":
            impacts.append("Stay focused on current execution phase")
        else:
            impacts.append("Continue planning based on your goal")
    
    return impacts[:3]


def _generate_recommendations(news_data: list[dict[str, Any]], goal: str, completed: int, streak: int) -> list[str]:
    """Generate specific action recommendations."""
    recommendations = []
    
    if not goal:
        recommendations.append("Set your first goal to get personalized recommendations")
        return recommendations
    
    goal_lower = goal.lower()
    high_urgency_count = len([n for n in news_data if n.get("urgency") == "high"])
    
    # Base on streak and completion
    if streak == 0:
        recommendations.append("Start with 25-min focused session tomorrow")
    elif streak < 3:
        recommendations.append(f"Build your streak - target 5 days this week")
    else:
        recommendations.append(f"Maintain momentum - you have {streak} day streak")
    
    # Base on news and goals
    if "ai" in goal_lower:
        if high_urgency_count > 0:
            recommendations.append("Review 1 new AI paper or tutorial this week")
        else:
            recommendations.append("Continue current AI learning path")
    
    if "job" in goal_lower:
        if high_urgency_count > 0:
            recommendations.append("Apply to 3 companies aligning with market trends")
        else:
            recommendations.append("Update resume with latest project")
    
    if "data" in goal_lower:
        recommendations.append("Practice SQL/Python for 30 min - high market demand")
    
    if completed == 0:
        recommendations.append("Start tomorrow with small, achievable task")
    elif completed >= 3:
        recommendations.append("Excellent day - maintain this pace tomorrow")
    
    return recommendations[:4]


def generate_daily_summary(user_id: str) -> dict[str, Any]:
    """Generate end-of-day intelligence report with insights and recommendations."""
    memory = load_user_memory(user_id) or {}
    streak = get_user_streak(user_id)
    current_streak = streak["current_streak"]
    trajectory = load_trajectory(user_id) or {}
    goal = memory.get("last_goal", "")
    
    # Track daily completions
    today_sessions = memory.get("today_sessions_completed", 0)
    today_missed = memory.get("today_sessions_missed", 0)
    
    # Get today's relevant news for analysis
    user_data = {"goal": goal, "trajectory": trajectory}
    news_data = get_priority_news(user_data)
    
    # Generate intelligence components
    key_takeaways = _extract_key_takeaways(news_data, goal)
    impact_for_user = _calculate_impact_for_user(news_data, goal, trajectory)
    recommendations = _generate_recommendations(news_data, goal, today_sessions, current_streak)
    
    # Build human-readable message
    if today_sessions > 0:
        message = f"Today: Completed {today_sessions}, Missed {today_missed}. Streak: {current_streak} days."
        if current_streak > 1:
            message += " You're improving. Stay consistent tomorrow."
        else:
            message += " Good start. Build on this."
    else:
        message = f"Today: No sessions completed. Streak: {current_streak} days. Start fresh tomorrow."
    
    # Reset daily counters
    memory["today_sessions_completed"] = 0
    memory["today_sessions_missed"] = 0
    save_user_memory(user_id, memory)
    
    logger.info(
        "bowa_summary user=%s completed=%d missed=%d streak=%d goal=%s",
        user_id, today_sessions, today_missed, current_streak, goal
    )
    
    return {
        "completed": today_sessions,
        "missed": today_missed,
        "streak": current_streak,
        "message": message,
        "key_takeaways": key_takeaways,
        "impact_for_user": impact_for_user,
        "what_you_should_do": recommendations,
    }