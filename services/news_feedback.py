"""News feedback and learning system for BOWA.

Captures user reactions, tracks follow-through, updates preference model,
and enables adaptive news scoring based on user engagement.
"""

import logging
import json
from datetime import datetime, timedelta
from typing import Any

from services.memory import load_user_memory, save_user_memory
from services.execution import get_execution_session

logger = logging.getLogger(__name__)


def _get_news_feedback_history(user_id: str) -> dict[str, Any]:
    """Load news feedback history from user memory."""
    memory = load_user_memory(user_id) or {}
    if "news_feedback_history" not in memory:
        memory["news_feedback_history"] = {}
    return memory.get("news_feedback_history", {})


def _save_news_feedback_history(user_id: str, history: dict[str, Any]) -> None:
    """Save news feedback history to user memory."""
    memory = load_user_memory(user_id) or {}
    memory["news_feedback_history"] = history
    save_user_memory(user_id, memory)


def _get_user_news_preferences(user_id: str) -> dict[str, Any]:
    """Load user news preferences and weights."""
    memory = load_user_memory(user_id) or {}
    if "news_preferences" not in memory:
        memory["news_preferences"] = {
            "topic_weights": {
                "AI": 1.0,
                "Jobs": 1.0,
                "Finance": 1.0,
                "General": 0.8,
            },
            "engagement_counts": {
                "AI": {"acted": 0, "watched": 0, "ignored": 0},
                "Jobs": {"acted": 0, "watched": 0, "ignored": 0},
                "Finance": {"acted": 0, "watched": 0, "ignored": 0},
                "General": {"acted": 0, "watched": 0, "ignored": 0},
            },
            "feedback_scores": {
                "AI": 0.5,
                "Jobs": 0.5,
                "Finance": 0.5,
                "General": 0.5,
            }
        }
        save_user_memory(user_id, memory)
    return memory.get("news_preferences", {})


def _save_user_news_preferences(user_id: str, preferences: dict[str, Any]) -> None:
    """Save user news preferences."""
    memory = load_user_memory(user_id) or {}
    memory["news_preferences"] = preferences
    save_user_memory(user_id, memory)


def capture_user_reaction(
    user_id: str,
    news_title: str,
    category: str,
    action_suggested: str,
    user_action: str,
    goal: str = "",
) -> dict[str, Any]:
    """Capture user's reaction to a news item.
    
    Args:
        user_id: User identifier
        news_title: Title of the news item
        category: Category (AI, Jobs, Finance, General)
        action_suggested: What we suggested (act, watch, ignore)
        user_action: What user did (clicked, read, ignored)
        goal: User's current goal
    """
    history = _get_news_feedback_history(user_id)
    
    news_id = f"{category}_{len(history)}"
    timestamp = datetime.utcnow().isoformat()
    
    feedback_entry = {
        "news_id": news_id,
        "title": news_title,
        "category": category,
        "action_suggested": action_suggested,
        "user_action": user_action,
        "timestamp": timestamp,
        "goal": goal,
        "follow_through": None,  # Will be updated in 24h check
    }
    
    history[news_id] = feedback_entry
    _save_news_feedback_history(user_id, history)
    
    logger.info(
        "bowa_news_feedback user=%s topic=%s action=%s follow_through=pending",
        user_id, category, user_action
    )
    
    return feedback_entry


def track_follow_through(user_id: str, max_hours: int = 24) -> dict[str, Any]:
    """Check which news items user acted on within time window.
    
    Returns dict with:
    - checked_items: count of items checked
    - acted_items: count where user followed through
    - follow_through_rate: percentage
    """
    history = _get_news_feedback_history(user_id)
    now = datetime.utcnow()
    checked = 0
    acted = 0
    
    for news_id, entry in history.items():
        if entry.get("follow_through") is not None:
            continue  # Already checked
        
        timestamp_str = entry.get("timestamp", "")
        try:
            timestamp = datetime.fromisoformat(timestamp_str)
            time_diff = (now - timestamp).total_seconds() / 3600
            
            # Only check items from time window
            if time_diff > max_hours:
                checked += 1
                
                # Check if user acted on this news
                action_suggested = entry.get("action_suggested", "")
                category = entry.get("category", "")
                
                if action_suggested == "act":
                    # Check if user started execution session or used related tools
                    session = get_execution_session(user_id)
                    user_acted = False
                    
                    if session and session.get("active"):
                        user_acted = True
                    
                    entry["follow_through"] = user_acted
                    if user_acted:
                        acted += 1
                    
                    logger.info(
                        "bowa_news_feedback user=%s topic=%s follow_through=%s",
                        user_id, category, user_acted
                    )
                else:
                    # For "watch" or "ignore", check if they read/interacted
                    entry["follow_through"] = entry.get("user_action") in ["read", "clicked"]
                    if entry["follow_through"]:
                        acted += 1
        except (ValueError, TypeError):
            continue
    
    _save_news_feedback_history(user_id, history)
    
    follow_through_rate = (acted / checked * 100) if checked > 0 else 0
    return {
        "checked_items": checked,
        "acted_items": acted,
        "follow_through_rate": follow_through_rate,
    }


def update_user_news_preferences(user_id: str) -> dict[str, Any]:
    """Update user preference model based on engagement history.
    
    Returns updated preference weights and scores.
    """
    history = _get_news_feedback_history(user_id)
    preferences = _get_user_news_preferences(user_id)
    
    engagement_counts = preferences.get("engagement_counts", {})
    topic_weights = preferences.get("topic_weights", {})
    feedback_scores = preferences.get("feedback_scores", {})
    
    # Analyze engagement by category
    category_actions = {}
    for news_id, entry in history.items():
        category = entry.get("category", "General")
        user_action = entry.get("user_action", "ignored")
        
        if category not in category_actions:
            category_actions[category] = {"acted": 0, "watched": 0, "ignored": 0}
        
        if user_action in ["acted", "clicked", "read"]:
            category_actions[category]["acted"] += 1
        elif user_action == "watched":
            category_actions[category]["watched"] += 1
        else:
            category_actions[category]["ignored"] += 1
    
    # Update weights based on engagement
    for topic, actions in category_actions.items():
        total = sum(actions.values())
        ignored_count = actions.get("ignored", 0)
        acted_count = actions.get("acted", 0)
        
        # If ignored 3+ times, reduce weight by 30%
        if ignored_count >= 3:
            topic_weights[topic] = max(0.5, topic_weights.get(topic, 1.0) * 0.7)
        
        # If acted on, increase weight by 20%
        if acted_count > 0:
            topic_weights[topic] = min(1.5, topic_weights.get(topic, 1.0) * 1.2)
        
        # Calculate feedback score (0-1)
        if total > 0:
            feedback_scores[topic] = acted_count / total
        
        # Update engagement counts
        engagement_counts[topic] = actions
    
    preferences["topic_weights"] = topic_weights
    preferences["engagement_counts"] = engagement_counts
    preferences["feedback_scores"] = feedback_scores
    _save_user_news_preferences(user_id, preferences)
    
    logger.info(
        "bowa_news_preferences user=%s weights=%s scores=%s",
        user_id, topic_weights, feedback_scores
    )
    
    return preferences


def get_preference_weight(user_id: str, topic: str) -> float:
    """Get current preference weight for a topic."""
    preferences = _get_user_news_preferences(user_id)
    weights = preferences.get("topic_weights", {})
    return weights.get(topic, 1.0)


def calculate_confidence_score(user_id: str, topic: str) -> float:
    """Calculate confidence score (0-100) for news recommendations.
    
    Based on past user engagement with similar news.
    """
    preferences = _get_user_news_preferences(user_id)
    feedback_scores = preferences.get("feedback_scores", {})
    engagement_counts = preferences.get("engagement_counts", {})
    
    # Get topic score (0-1)
    topic_score = feedback_scores.get(topic, 0.5)
    
    # Get engagement count for topic
    topic_engagement = engagement_counts.get(topic, {})
    total_engagements = sum(topic_engagement.values())
    
    # Boost confidence if high engagement
    confidence_base = topic_score * 100  # 0-100
    
    # Add engagement factor (more data = more confidence)
    engagement_factor = min(20, total_engagements * 2)  # Up to +20 for high engagement
    confidence = min(100, confidence_base + engagement_factor)
    
    return max(0, confidence)


def capture_feedback(
    user_id: str,
    news_id: str,
    feedback: str,  # "positive" or "negative"
    topic: str = "",
) -> dict[str, Any]:
    """Capture explicit user feedback (thumbs up/down).
    
    Args:
        user_id: User identifier
        news_id: News item identifier
        feedback: "positive" or "negative"
        topic: News category
    """
    preferences = _get_user_news_preferences(user_id)
    feedback_scores = preferences.get("feedback_scores", {})
    
    if feedback == "positive":
        # Boost score for this topic
        if topic:
            current_score = feedback_scores.get(topic, 0.5)
            feedback_scores[topic] = min(0.95, current_score + 0.1)
        logger.info("bowa_news_feedback user=%s topic=%s action=positive", user_id, topic)
    else:  # negative
        # Reduce score for this topic
        if topic:
            current_score = feedback_scores.get(topic, 0.5)
            feedback_scores[topic] = max(0.1, current_score - 0.15)
        logger.info("bowa_news_feedback user=%s topic=%s action=negative", user_id, topic)
    
    preferences["feedback_scores"] = feedback_scores
    _save_user_news_preferences(user_id, preferences)
    
    return {
        "status": "feedback_captured",
        "news_id": news_id,
        "feedback": feedback,
        "topic": topic,
    }


def get_adaptive_score(
    user_id: str,
    base_score: float,
    category: str,
) -> float:
    """Apply user preference weight to news score.
    
    score = base_score * user_preference_weight
    """
    weight = get_preference_weight(user_id, category)
    return base_score * weight


def suggest_action(
    user_id: str,
    base_score: float,
    category: str,
) -> str:
    """Suggest action based on confidence and score.
    
    Returns: "act", "watch", or "ignore"
    """
    confidence = calculate_confidence_score(user_id, category)
    
    # High confidence + high score = "act"
    if confidence >= 70 and base_score >= 75:
        return "act"
    
    # Medium confidence or medium score = "watch"
    if confidence >= 40 or base_score >= 50:
        return "watch"
    
    # Low confidence or low score = "ignore"
    return "ignore"


def get_user_news_stats(user_id: str) -> dict[str, Any]:
    """Get comprehensive news engagement statistics."""
    preferences = _get_user_news_preferences(user_id)
    history = _get_news_feedback_history(user_id)
    follow_through = track_follow_through(user_id)
    
    return {
        "preferences": preferences,
        "engagement_counts": preferences.get("engagement_counts", {}),
        "topic_weights": preferences.get("topic_weights", {}),
        "feedback_scores": preferences.get("feedback_scores", {}),
        "follow_through": follow_through,
        "total_feedback_items": len(history),
    }
