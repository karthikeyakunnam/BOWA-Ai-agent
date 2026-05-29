"""News feedback and learning system for BOWA.

Captures user reactions, tracks follow-through, updates preference model,
and enables adaptive news scoring based on user engagement.
"""

import logging
import json
import math
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

    if user_action == "clicked":
        from event_timeline import append_event
        append_event(user_id, "news_clicked", {"title": news_title, "category": category})
    
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


def evaluate_news_impact(user_id: str, news_id: str, outcome: str = None) -> str:
    """Evaluate or ask for impact of news action."""
    memory = load_user_memory(user_id) or {}
    stats = memory.get("news_action_stats", {})
    
    # If outcome provided, infer impact
    if outcome:
        if outcome == "completed":
            completed_count = stats.get("completed_actions", 0)
            if completed_count >= 3:  # Repeated engagement
                return "high"
            return "medium"
        elif outcome == "partial":
            return "medium"
        elif outcome == "abandoned":
            return "low"
    
    # Check if we have recent impact data
    last_impact = stats.get("last_impact")
    if last_impact and stats.get("total_actions", 0) > 0:
        return last_impact
    
    # Default to medium if no data
    return "medium"


def _apply_impact_normalization(user_id: str, impact_score: int) -> int:
    """Apply normalization to prevent drift."""
    return min(max(impact_score, 0), 100)


def _check_diminishing_returns(user_id: str, category: str, impact: str) -> float:
    """Apply diminishing returns for repeated high impacts on same topic."""
    memory = load_user_memory(user_id) or {}
    topic_history = memory.get("topic_impact_history", {})
    
    if category not in topic_history:
        topic_history[category] = []
        memory["topic_impact_history"] = topic_history
    
    recent_impacts = topic_history[category][-3:]  # Last 3 impacts
    high_count = sum(1 for imp in recent_impacts if imp.get("impact") == "high")
    
    if impact == "high" and high_count >= 3:
        return 0.5  # Reduce bonus by 50%
    
    return 1.0


def _apply_abandoned_penalty(user_id: str) -> int:
    """Apply extra penalty for consecutive abandoned tasks."""
    memory = load_user_memory(user_id) or {}
    stats = memory.get("news_action_stats", {})
    
    # Check recent outcomes
    recent_outcomes = stats.get("recent_outcomes", [])
    abandoned_count = 0
    
    for outcome in reversed(recent_outcomes[-5:]):  # Check last 5
        if outcome == "abandoned":
            abandoned_count += 1
        else:
            break
    
    if abandoned_count >= 2:
        return -5  # Extra penalty
    
    return 0


def _calculate_time_decay(user_id: str, impact_entry: dict[str, Any]) -> float:
    """Calculate time decay factor for impact."""
    try:
        timestamp = datetime.fromisoformat(impact_entry.get("timestamp", ""))
        days_since = (datetime.now() - timestamp).total_seconds() / (24 * 3600)
        decay_factor = math.exp(-days_since * 0.1)
        return decay_factor
    except (ValueError, TypeError):
        return 1.0


def get_effective_impact_score(user_id: str) -> float:
    """Calculate effective impact score with time decay."""
    memory = load_user_memory(user_id) or {}
    stats = memory.get("news_action_stats", {})
    
    base_impact = stats.get("impact_score", 50)
    
    # Apply time decay to recent impacts
    topic_history = memory.get("topic_impact_history", {})
    total_weighted_score = 0
    total_weight = 0
    
    for category, impacts in topic_history.items():
        for impact_entry in impacts[-10:]:  # Last 10 per topic
            decay_factor = _calculate_time_decay(user_id, impact_entry)
            impact_value = {"high": 80, "medium": 50, "low": 20}[impact_entry.get("impact", "medium")]
            weighted_score = impact_value * decay_factor
            total_weighted_score += weighted_score
            total_weight += decay_factor
    
    if total_weight > 0:
        effective_impact = total_weighted_score / total_weight
        return effective_impact
    
    return base_impact


def update_impact_from_feedback(user_id: str, news_id: str, user_impact: str, category: str = "General") -> None:
    """Update impact based on explicit user feedback with calibration."""
    memory = load_user_memory(user_id) or {}
    
    if "news_action_stats" not in memory:
        memory["news_action_stats"] = {
            "impact_score": 50,
            "last_impact": "medium",
            "recent_outcomes": []
        }
    
    stats = memory["news_action_stats"]
    stats["last_impact"] = user_impact
    
    # Update impact_score with diminishing returns
    new_score = {"high": 80, "medium": 50, "low": 20}[user_impact]
    diminishing_factor = _check_diminishing_returns(user_id, category, user_impact)
    adjusted_score = int(new_score * diminishing_factor)
    
    # Apply abandoned penalty
    penalty = _apply_abandoned_penalty(user_id)
    adjusted_score += penalty
    
    # Weighted average with normalization
    if stats.get("total_actions", 0) == 0:
        stats["impact_score"] = _apply_impact_normalization(user_id, adjusted_score)
    else:
        stats["impact_score"] = _apply_impact_normalization(
            user_id, 
            int((stats["impact_score"] * 0.7) + (adjusted_score * 0.3))
        )
    
    # Track per-topic impact history
    if "topic_impact_history" not in memory:
        memory["topic_impact_history"] = {}
    
    topic_history = memory["topic_impact_history"]
    if category not in topic_history:
        topic_history[category] = []
    
    topic_history[category].append({
        "impact": user_impact,
        "timestamp": datetime.now().isoformat(),
        "news_id": news_id
    })
    
    # Keep only last 20 per topic
    topic_history[category] = topic_history[category][-20:]
    
    save_user_memory(user_id, memory)
    
    # Update confidence_score from impact
    from services.execution import _update_confidence_from_impact
    _update_confidence_from_impact(user_id, user_impact)


def get_user_news_stats(user_id: str) -> dict[str, Any]:
    """Get comprehensive news engagement statistics."""
    preferences = _get_user_news_preferences(user_id)
    history = _get_news_feedback_history(user_id)
    follow_through = track_follow_through(user_id)
    
    # Get impact stats
    memory = load_user_memory(user_id) or {}
    stats = memory.get("news_action_stats", {})
    
    return {
        "preferences": preferences,
        "engagement_counts": preferences.get("engagement_counts", {}),
        "topic_weights": preferences.get("topic_weights", {}),
        "feedback_scores": preferences.get("feedback_scores", {}),
        "follow_through": follow_through,
        "total_feedback_items": len(history),
        "impact_score": stats.get("impact_score", 50),
        "last_impact": stats.get("last_impact", "medium"),
    }
