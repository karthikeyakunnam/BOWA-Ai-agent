"""End-of-day news summary generator for BOWA."""

import json
from datetime import datetime, timezone
from typing import Any

from services.news_service import get_priority_news
from services.llm import generate_response
from services.memory import load_user_memory


def generate_daily_news_summary(user_id: str) -> dict[str, Any]:
    """
    Generate an intelligent end-of-day summary using the LLM.
    Parses today's news and generates key takeaways, user impact, and recommendations.
    """
    user_data = load_user_memory(user_id)
    goal = user_data.get("goal", "improve my skills")
    
    # Fetch today's news
    articles = get_priority_news(user_data)
    
    if not articles:
        return {
            "key_takeaways": ["No significant news tracked today."],
            "impact_for_user": ["No immediate impact."],
            "what_you_should_do": ["Continue with your standard plan."]
        }

    # Extract top 10 most relevant news items to feed the LLM
    news_text = "\n".join(
        [f"- {a['title']} ({a.get('category', 'General')}): {a.get('summary', '')}" for a in articles[:10]]
    )

    prompt = f"""You are BOWA's Intelligence Engine. 
Analyze the following news from today and generate a highly personalized daily summary for the user.

User Goal: {goal}

Today's News:
{news_text}

You must output valid JSON matching this exact structure:
{{
  "key_takeaways": [
    "string: high level global takeaway 1",
    "string: high level global takeaway 2"
  ],
  "impact_for_user": [
    "string: how this specifically impacts the user's goal 1",
    "string: how this specifically impacts the user's goal 2"
  ],
  "what_you_should_do": [
    "string: highly specific action 1 based on the news",
    "string: highly specific action 2 based on the news"
  ]
}}

Do not include markdown code blocks, just raw JSON."""

    messages = [{"role": "system", "content": prompt}]
    
    try:
        raw_reply = generate_response(messages)
        clean_reply = raw_reply.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(clean_reply)
    except Exception:
        # Fallback if LLM fails
        parsed = {
            "key_takeaways": ["Unable to generate insights today."],
            "impact_for_user": ["News processing failed."],
            "what_you_should_do": ["Stay focused on your current tasks."]
        }

    return parsed
