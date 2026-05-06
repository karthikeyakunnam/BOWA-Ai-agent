"""News intelligence service for BOWA."""

import os
import logging
from typing import Any
import requests
from dotenv import load_dotenv
from diskcache import Cache

# Set up a cache that expires every hour
cache = Cache("cache_dir")

load_dotenv()

NEWS_API_KEY = os.getenv("NEWS_API_KEY")


def fetch_news() -> list[dict[str, Any]]:
    """Fetch latest news from NewsAPI with caching."""
    cache_key = "news_data"
    if cache_key in cache:
        return cache[cache_key]

    if not NEWS_API_KEY:
        return []

    url = "https://newsapi.org/v2/everything"
    params = {
        "q": "AI OR jobs OR finance OR stock OR technology",
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": 10,
        "apiKey": NEWS_API_KEY
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get("status") == "error":
            return []

        articles = data.get("articles", [])
        cache.set(cache_key, articles, expire=3600)
        return articles
    except requests.exceptions.RequestException:
        return []


def filter_news(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter and deduplicate news articles."""
    seen_titles = set()
    filtered = []

    for article in articles:
        title = article.get("title")
        if title and title not in seen_titles:
            filtered.append(article)
            seen_titles.add(title)

    return filtered[:5]


def get_article_text(article: dict[str, Any]) -> str:
    """Extract searchable text from article title and description."""
    title = article.get("title") or ""
    description = article.get("description") or ""
    return f"{title} {description}".lower()


def contains_keyword(text: str, keywords: list[str]) -> bool:
    """Check whether text contains any keyword."""
    return any(keyword in text for keyword in keywords)


def classify_news(article: dict[str, Any]) -> str:
    """Classify a news article into a BOWA category."""
    article_text = get_article_text(article)

    if contains_keyword(article_text, ["ai", "machine learning"]):
        return "AI"
    if contains_keyword(article_text, ["hiring", "layoffs"]):
        return "Jobs"
    if contains_keyword(article_text, ["stock", "market", "economy"]):
        return "Finance"

    return "General"


def assign_priority(article: dict[str, Any]) -> str:
    """Assign priority based on title and description keywords."""
    article_text = get_article_text(article)

    high_priority_keywords = [
        "layoffs",
        "hiring freeze",
        "market crash",
        "major ai breakthrough"
    ]
    medium_priority_keywords = [
        "product launch",
        "product launches",
        "launches",
        "launch",
        "moderate update",
        "moderate updates",
        "update",
        "updates"
    ]

    if contains_keyword(article_text, high_priority_keywords):
        return "HIGH"
    if contains_keyword(article_text, medium_priority_keywords):
        return "MEDIUM"

    return "LOW"


def get_action(priority: str) -> str:
    """Return action guidance for a news priority."""
    actions = {
        "HIGH": "Act or pay attention immediately",
        "MEDIUM": "Keep an eye on this",
        "LOW": "No action needed"
    }

    return actions.get(priority, "No action needed")

def get_why(category: str, priority: str) -> str:
    """Generate a brief explanation of why the news matters."""
    if priority == "HIGH":
        if category == "Jobs": return "Major industry shifts could impact your immediate job search strategy."
        if category == "AI": return "Breakthroughs or major changes could redefine technical requirements."
        if category == "Finance": return "Economic shocks directly impact startup funding and hiring budgets."
        return "Critical updates that require your immediate attention."
    
    if category == "Jobs": return "Trends suggest shifting demand in the market."
    if category == "AI": return "New tools or updates could be worth learning soon."
    if category == "Finance": return "Market movements signal broader industry health."
    return "General industry context to keep you informed."


def process_news(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Classify, prioritize, and enrich news articles for API output."""
    processed_articles = []
    
    for article in articles:
        priority = assign_priority(article)
        category = classify_news(article)
        
        # Format time if possible
        time_str = article.get("publishedAt", "Unknown time")
        
        processed_articles.append({
            "title": article.get("title", "N/A"),
            "summary": article.get("description", ""),
            "source": article.get("source", {}).get("name", "Unknown Source"),
            "url": article.get("url", "#"),
            "time": time_str,
            "category": category,
            "priority": priority.lower(),
            "why": get_why(category, priority)
        })

    return processed_articles


def filter_news_for_user(user_data: dict[str, Any], news_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter and score news based on user goal."""
    goal = user_data.get("goal", "").lower() if user_data else ""
    trajectory = user_data.get("trajectory", {}) if user_data else {}
    stage = trajectory.get("current_stage", "Planning").lower()
    
    target_categories = set()
    if "ai" in goal or "data" in goal: target_categories.add("AI")
    if "job" in goal or "hire" in goal: target_categories.add("Jobs")
    
    for item in news_list:
        score = 50
        cat = item["category"]
        text = f"{item['title']} {item['summary']}".lower()
        
        if cat in target_categories:
            score += 25
        
        # Keyword matching
        if goal:
            goal_words = set(goal.split())
            text_words = set(text.split())
            matches = len(goal_words.intersection(text_words))
            score += min(20, matches * 5)
            
        # Recent activity/stage bonus
        if stage == "execution" and item["priority"] == "high":
            score += 5
            
        item["relevance_score"] = min(100, score)

    # Sort high relevance -> medium -> low
    news_list.sort(key=lambda x: (x.get("relevance_score", 0), x["priority"] == "high", x["priority"] == "medium"), reverse=True)
    return news_list


def get_priority_news(user_data: dict[str, Any] = None) -> list[dict[str, Any]]:
    """Fetch, filter, classify, score, and return structured news list."""
    articles = fetch_news()
    filtered_articles = filter_news(articles)
    processed = process_news(filtered_articles)
    return filter_news_for_user(user_data, processed)
