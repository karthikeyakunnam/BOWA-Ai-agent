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
Analyze today's news and generate a decision-focused summary.

User Goal: {goal}

Today's News:
{news_text}

Rules: CONCISE - DECISION-FOCUSED - MAX 6 LINES

Output valid JSON:
{{
  "decisions_you_should_have_taken": [
    "decision 1",
    "decision 2", 
    "decision 3"
  ],
  "what_you_did": [
    "completed: action1",
    "partial: action2"
  ],
  "what_you_missed": [
    "high-urgency item not acted on"
  ],
  "next_day_focus": [
    "priority item 1",
    "priority item 2"
  ]
}}

No markdown, raw JSON only."""

    messages = [{"role": "system", "content": prompt}]
    
    try:
        raw_reply = generate_response(messages)
        clean_reply = raw_reply.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(clean_reply)
    except Exception:
        # Fallback if LLM fails
        parsed = {
            "decisions_you_should_have_taken": ["Review news manually", "Check key sources", "Plan next actions"],
            "what_you_did": ["No news actions completed today"],
            "what_you_missed": ["Unable to analyze missed opportunities"],
            "next_day_focus": ["Focus on current priorities", "Review news sources"]
        }

    # Store summary for behavior correction
    memory = load_user_memory(user_id) or {}
    memory["last_daily_summary"] = parsed
    save_user_memory(user_id, memory)

    return parsed
