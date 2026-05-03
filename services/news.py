"""News intelligence service for BOWA."""

import os
from typing import Any

import requests
from dotenv import load_dotenv


load_dotenv()

NEWS_API_KEY = os.getenv("NEWS_API_KEY")


def fetch_news() -> list[dict[str, Any]]:
    """Fetch latest news from NewsAPI."""
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

        return data.get("articles", [])
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


def process_news(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Classify, prioritize, and enrich news articles for API output."""
    processed_articles = []
    priority_rank = {
        "HIGH": 3,
        "MEDIUM": 2,
        "LOW": 1
    }

    for article in articles:
        priority = assign_priority(article)
        processed_articles.append({
            "title": article.get("title", "N/A"),
            "description": article.get("description", ""),
            "category": classify_news(article),
            "priority": priority,
            "action": get_action(priority),
            "source": article.get("source", {}).get("name", "N/A"),
            "url": article.get("url", "N/A")
        })

    processed_articles.sort(
        key=lambda article: priority_rank.get(article["priority"], 0),
        reverse=True
    )
    return processed_articles


def get_priority_news() -> list[dict[str, Any]]:
    """Fetch, filter, classify, and prioritize news articles."""
    articles = fetch_news()
    filtered_articles = filter_news(articles)
    return process_news(filtered_articles)
