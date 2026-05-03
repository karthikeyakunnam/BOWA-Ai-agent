"""Message-driven conversation engine for BOWA.

Core rule: response = f(user_message, user_state, mode)

Intent is ALWAYS detected from the message first. Mode is only
a fallback when intent is unclear. Greetings get human replies,
not data dumps. Unclear messages get pushed for clarity.

No external AI APIs. All logic is deterministic.
"""

from __future__ import annotations

import random
from typing import Any

from services.behavior import generate_action_plan
from services.formatter import (
    format_job_full_response,
    format_news,
    format_study_with_news,
    format_tracker_confirm,
)
from services.insights import generate_insights
from services.jobs import fetch_jobs, filter_jobs, get_skill_gap_analysis
from services.memory import load_user_memory, update_user_memory
from services.news import get_priority_news
from services.state import (
    build_initial_state,
    get_user_state,
    reset_state,
    update_user_state,
)
from services.student import get_student_roadmap


# ── Intent detection ───────────────────────────────────────────────────
#
# This drives EVERYTHING. The mode selector is just a fallback.

_INTENT_KEYWORDS: dict[str, list[str]] = {
    "greeting": [
        "hi", "hello", "hey", "sup", "yo", "good morning",
        "good evening", "what's up", "howdy",
    ],
    "study": [
        "study", "learn", "roadmap", "exam", "course", "semester",
        "syllabus", "revision", "prepare", "studying", "learning",
        "education", "academic", "college", "university", "subject",
    ],
    "job": [
        "job", "career", "hiring", "interview", "resume",
        "placement", "company", "intern", "internship",
        "apply", "application", "salary", "recruit",
    ],
    "planning": [
        "plan", "schedule", "track", "organize", "routine",
        "to-do", "todo", "daily plan", "plan my day",
        "plan today", "timer",
    ],
    "news": [
        "news", "headline", "what's happening", "update",
        "trending", "latest", "current affairs", "what happened",
    ],
    "emotion": [
        "confused", "lost", "stuck", "tired", "bored",
        "don't know", "idk", "help", "nothing", "hmm",
        "what should i do",
    ],
}


def detect_intent(message: str) -> str:
    """Detect intent from the actual message content.

    Returns: greeting, study, job, planning, news, emotion, or unclear.
    """
    msg = message.lower().strip()

    # Exact short matches first (prevents "hi" matching inside words)
    short_greetings = {"hi", "hello", "hey", "sup", "yo", "howdy"}
    if msg in short_greetings:
        return "greeting"

    # Keyword scan — order matters (planning before study to catch "plan")
    scan_order = ["planning", "news", "study", "job", "greeting", "emotion"]
    for intent in scan_order:
        keywords = _INTENT_KEYWORDS[intent]
        for kw in keywords:
            # Use word-boundary-aware matching for short keywords
            if len(kw) <= 3:
                # Short keyword: must be a standalone word
                words = msg.split()
                if kw in words:
                    return intent
            else:
                if kw in msg:
                    return intent

    return "unclear"


def _mode_from_select(mode: str) -> str:
    """Normalize the frontend mode selector value."""
    return {
        "Study": "study",
        "Jobs": "job",
        "News": "news",
        "Tracker": "planning",
        "General": "general",
    }.get(mode, "general")


# ── Greeting handler ──────────────────────────────────────────────────
#
# Short. Human. No data dumps. Just acknowledge and push forward.

_GREETING_REPLIES = [
    "Yeah. Tell me what you're actually trying to fix.",
    "Hey. What are we working on today?",
    "Good you showed up. Now — what do you need?",
    "I'm here. Study, jobs, or something else?",
    "Alright. What's the move today — study, career, or just need news?",
]

_GREETING_REPLIES_WITH_MEMORY = [
    "Back again. Still working on {goal}? Or something new?",
    "Hey. Last time you were focused on {goal}. Continuing that?",
    "Welcome back. {goal} — still the target? Or we switching?",
]

_EMOTION_REPLIES = [
    "I hear you. But sitting here won't fix it.\nWhat's the ONE thing you want to sort out right now?",
    "Okay. Let's not overthink this.\nJust tell me — study, job, or need a plan for today?",
    "Everyone gets stuck. The fix is simple: pick one thing and start.\nWhat's it gonna be?",
    "Low energy? Fine. Let's do something small.\nEven 30 minutes on one task beats doing nothing.\nWhat should we tackle?",
]

_UNCLEAR_REPLIES = [
    "Be specific. What do you need — study, job, or planning?",
    "That's vague. What exactly are you trying to improve?",
    "I need more to work with. Study help? Job search? Daily plan?",
    "Not sure what you mean. Try: 'help me study' or 'find me a job'.",
]

_UNCLEAR_WITH_MODE = {
    "study": "You're in study mode but I'm not sure what you need.\nTry: 'help me study CSE' or 'I want to learn AI'.",
    "job": "You're in job mode. Tell me something like:\n'I want a frontend developer role' or 'find me jobs'.",
    "news": "Want news? Just say 'show me news' or 'what's happening today'.",
    "planning": "Planning mode. Try: 'plan my day' or 'schedule 2 hours of DSA'.",
}


def _handle_greeting(user_id: str, message: str) -> str:
    """Natural, human greeting response. No data dumps."""
    memory = load_user_memory(user_id)
    goal = memory.get("goal", "")

    if goal and _GREETING_REPLIES_WITH_MEMORY:
        return random.choice(_GREETING_REPLIES_WITH_MEMORY).format(goal=goal)

    return random.choice(_GREETING_REPLIES)


def _handle_emotion(user_id: str, message: str) -> str:
    """Handle confused/tired/stuck messages with a push."""
    return random.choice(_EMOTION_REPLIES)


def _handle_unclear(user_id: str, message: str, mode: str) -> str:
    """Handle unclear messages — use mode as context hint."""
    mode_hint = _UNCLEAR_WITH_MODE.get(mode)
    if mode_hint and mode != "general":
        return mode_hint
    return random.choice(_UNCLEAR_REPLIES)


# ── Study mode ─────────────────────────────────────────────────────────

def _handle_study(
    user_id: str,
    message: str,
    state: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Multi-stage study flow. Each call handles exactly one stage."""
    data = state["data"]
    stage = state["stage"]

    # ── Init: ask for topic ──
    if stage == "init":
        state["stage"] = "ask_topic"
        update_user_state(user_id, state)
        return (
            "Alright, let's get you a study plan.\n\n"
            "What are you studying?\n"
            "(e.g., CSE, ECE, Mechanical, or a specific subject)",
            state,
        )

    # ── Receive topic, ask for goal ──
    if stage == "ask_topic":
        data["topic"] = message.strip()
        state["stage"] = "ask_goal"
        update_user_state(user_id, state)
        return (
            f"{data['topic']}. Got it.\n\n"
            "And what's the end goal here?\n"
            "(e.g., Data Analyst, AI Engineer, Full Stack Developer)",
            state,
        )

    # ── Receive goal, generate plan ──
    if stage == "ask_goal":
        data["goal"] = message.strip()

        roadmap = get_student_roadmap(data["topic"])
        news = get_priority_news()

        update_user_memory(user_id, {
            "user_type": "student",
            "branch": data["topic"],
            "goal": data["goal"],
        })

        response = format_study_with_news(roadmap, data["goal"], news)
        response += "\n\nNow — how many hours can you commit daily?"

        state["stage"] = "ask_hours"
        update_user_state(user_id, state)
        return response, state

    # ── Receive hours, generate action plan ──
    if stage == "ask_hours":
        data["hours"] = message.strip()

        user_skills = load_user_memory(user_id).get("skills", [])
        gap = get_skill_gap_analysis(data["goal"], user_skills)
        insights = generate_insights({"goal": data["goal"]}, gap)
        action_plan = generate_action_plan(insights, gap)

        days = action_plan.get("days", [])
        missing = gap.get("missing_skills", [])

        lines = [f"Locked in. {data['hours']} hours/day.\n"]
        lines.append("Your 5-day action plan:\n")
        for day in days:
            lines.append(f"  Day {day['day']}: {day['task']}")

        if missing:
            lines.append(f"\nYou're missing: {', '.join(missing)}")
        lines.append(f"Readiness: {insights.get('readiness', '0%')}")
        lines.append("\nStick to this. Come back after Day 1.")

        state["stage"] = "active"
        update_user_state(user_id, state)
        return "\n".join(lines), state

    # ── Active: already has a plan ──
    return (
        f"You're already set up — {data.get('topic', '?')} "
        f"for {data.get('goal', '?')}.\n\n"
        "Want me to refresh your plan, check jobs, or show news?\n"
        "Just tell me what you need.",
        state,
    )


# ── Job mode ───────────────────────────────────────────────────────────

INDIA_CITIES = {
    "bangalore": "Karnataka", "bengaluru": "Karnataka",
    "hyderabad": "Telangana", "chennai": "Tamil Nadu",
    "pune": "Maharashtra", "mumbai": "Maharashtra",
    "delhi": "Delhi NCR", "noida": "Delhi NCR",
    "gurugram": "Delhi NCR", "kolkata": "West Bengal",
    "kochi": "Kerala",
}

ABROAD_COUNTRIES = {
    "usa": ["San Francisco", "New York", "Seattle", "Austin"],
    "uk": ["London", "Manchester", "Edinburgh"],
    "canada": ["Toronto", "Vancouver", "Montreal"],
    "germany": ["Berlin", "Munich", "Hamburg"],
    "australia": ["Sydney", "Melbourne"],
    "singapore": ["Singapore"],
    "uae": ["Dubai", "Abu Dhabi"],
}


def _is_technical(role: str) -> bool:
    """Detect if a role is technical or non-technical."""
    tech_keywords = [
        "developer", "engineer", "programmer", "devops", "data",
        "machine learning", "ai", "backend", "frontend", "full stack",
        "cloud", "qa", "automation", "database", "python", "java",
        "software", "web", "mobile", "ios", "android", "security",
    ]
    return any(kw in role.lower() for kw in tech_keywords)


def _handle_job(
    user_id: str,
    message: str,
    state: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Multi-stage job flow. Each call handles exactly one stage."""
    data = state["data"]
    stage = state["stage"]

    # ── Init: ask for role ──
    if stage == "init":
        state["stage"] = "ask_role"
        update_user_state(user_id, state)
        return (
            "Let's figure out your next move.\n\n"
            "What role are you targeting?\n"
            "(e.g., Frontend Developer, Data Analyst, AI Engineer)",
            state,
        )

    # ── Receive role, ask for skills ──
    if stage == "ask_role":
        data["role"] = message.strip()
        data["goal"] = data["role"]

        tech = _is_technical(data["role"])
        hint = (
            "(comma-separated, e.g., Python, SQL, React, Docker)"
            if tech else
            "(comma-separated, e.g., Communication, Excel, Analytics)"
        )

        state["stage"] = "ask_skills"
        update_user_state(user_id, state)
        return (
            f"{data['role']}. "
            f"{'Technical' if tech else 'Non-technical'} — noted.\n\n"
            f"What skills do you have right now?\n{hint}",
            state,
        )

    # ── Receive skills, ask for location ──
    if stage == "ask_skills":
        data["skills"] = [
            s.strip() for s in message.split(",") if s.strip()
        ]
        state["stage"] = "ask_location"
        update_user_state(user_id, state)
        return (
            f"Got it: {', '.join(data['skills'])}\n\n"
            "Where do you want to work?\n"
            "  1. India\n"
            "  2. Abroad\n"
            "  3. Both / Remote",
            state,
        )

    # ── Receive location, generate results ──
    if stage == "ask_location":
        data["location"] = message.strip().lower()

        update_user_memory(user_id, {
            "user_type": "job_seeker",
            "role": data["role"],
            "goal": data["role"],
            "skills": data["skills"],
        })

        jobs = fetch_jobs()
        matched = filter_jobs(jobs, data["role"])
        gap = get_skill_gap_analysis(data["role"], data["skills"])
        insights = generate_insights(
            {"goal": data["role"], "skills": data["skills"]}, gap,
        )

        response = format_job_full_response(matched, data["role"], gap, insights)

        loc = data.get("location", "")
        if "india" in loc or loc == "1":
            lines = ["\n\nTop cities in India:"]
            locs = {j.get("location", ""): j.get("company", "") for j in matched[:5]}
            if locs:
                for place, co in locs.items():
                    lines.append(f"  → {place} ({co})")
            else:
                for city, st in list(INDIA_CITIES.items())[:5]:
                    lines.append(f"  → {city.title()}, {st}")
            response += "\n".join(lines)

        elif "abroad" in loc or loc == "2":
            lines = ["\n\nTop locations abroad:"]
            for country, cities in list(ABROAD_COUNTRIES.items())[:4]:
                lines.append(f"  → {country.upper()}: {', '.join(cities[:2])}")
            response += "\n".join(lines)
        else:
            response += "\n\nCast a wide net — look at India + remote roles."

        state["stage"] = "active"
        update_user_state(user_id, state)
        return response, state

    # ── Active ──
    return (
        f"Already set up for {data.get('role', '?')}.\n"
        "Need a refresh, or switching to something else?",
        state,
    )


# ── News mode ──────────────────────────────────────────────────────────

def _handle_news(
    user_id: str,
    message: str,
    state: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Deliver only relevant, high-priority news."""
    news = get_priority_news()
    response = format_news(news)

    memory = load_user_memory(user_id)
    goal = memory.get("goal", "")

    if goal:
        response += f"\n\nFiltered for your goal: {goal}.\nAnything you want to dig into?"
    else:
        response += "\n\nTell me your field and I'll filter better next time."

    reset_state(user_id)
    return response, build_initial_state("general")


# ── Planning/Tracker mode ─────────────────────────────────────────────

def _handle_planning(
    user_id: str,
    message: str,
    state: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Multi-stage task planner."""
    data = state["data"]
    stage = state["stage"]

    if stage == "init":
        state["stage"] = "ask_task"
        update_user_state(user_id, state)
        return (
            "What exactly do you want to plan today?\n"
            "(e.g., DSA practice, project work, resume building)",
            state,
        )

    if stage == "ask_task":
        data["task"] = message.strip()
        state["stage"] = "ask_hours"
        update_user_state(user_id, state)
        return (
            f"'{data['task']}' — how many hours are you putting into this?",
            state,
        )

    if stage == "ask_hours":
        data["hours"] = message.strip()

        update_user_memory(user_id, {
            "current_task": data["task"],
            "daily_hours": data["hours"],
        })

        response = format_tracker_confirm(data["task"], data["hours"])
        reset_state(user_id)
        return response, build_initial_state("general")

    return "What task do you want to plan?", state


# ── Handler registry ──────────────────────────────────────────────────

_FLOW_HANDLERS: dict[str, Any] = {
    "study": _handle_study,
    "job": _handle_job,
    "news": _handle_news,
    "planning": _handle_planning,
}


# ── Main entry point ──────────────────────────────────────────────────

def handle_user_message(
    user_id: str,
    message: str,
    mode: str,
) -> dict[str, Any]:
    """Process a user message and return conversational reply.

    Core logic:
        response = f(user_message, user_state, mode)

    1. Detect intent from message (ALWAYS)
    2. If mid-flow, check if user wants to switch
    3. Intent drives response — mode is only fallback
    4. Greetings get human replies, not data dumps
    5. Unclear messages get pushed for clarity
    """
    state = get_user_state(user_id)
    intent = detect_intent(message)
    mode_normalized = _mode_from_select(mode)

    # ── Mid-flow: user is answering a question ──
    if state and state.get("stage") not in (None, "init", "active"):
        current_mode = state["mode"]

        # Only switch modes if user explicitly uses a keyword
        # (not a short/numeric answer that happens to match)
        msg_lower = message.lower().strip()
        is_short_answer = len(msg_lower) <= 3 or msg_lower.replace(".", "").isdigit()

        if (
            not is_short_answer
            and intent in ("study", "job", "news", "planning")
            and intent != current_mode
        ):
            state = build_initial_state(intent)
            update_user_state(user_id, state)
            handler = _FLOW_HANDLERS[intent]
            reply, state = handler(user_id, message, state)
            return {"reply": reply, "state": state}

        # If greeting mid-flow, don't break the flow — just nudge
        if intent == "greeting":
            return {
                "reply": "Hey — we're in the middle of something.\nJust answer the question above and we'll keep going.",
                "state": state,
            }

        # Otherwise, continue current flow
        handler = _FLOW_HANDLERS.get(current_mode)
        if handler:
            reply, state = handler(user_id, message, state)
            return {"reply": reply, "state": state}

    # ── Active state: previous flow completed ──
    if state and state.get("stage") == "active":
        current_mode = state["mode"]

        # Intent takes priority over stale active state
        if intent in _FLOW_HANDLERS:
            state = build_initial_state(intent)
            update_user_state(user_id, state)
            handler = _FLOW_HANDLERS[intent]
            reply, state = handler(user_id, message, state)
            return {"reply": reply, "state": state}

        if intent == "greeting":
            reply = _handle_greeting(user_id, message)
            return {"reply": reply, "state": state}

        if intent == "emotion":
            reply = _handle_emotion(user_id, message)
            return {"reply": reply, "state": state}

        # Unclear in active state — prompt based on current mode
        handler = _FLOW_HANDLERS.get(current_mode)
        if handler:
            reply, state = handler(user_id, message, state)
            return {"reply": reply, "state": state}

    # ── Fresh / general conversation: intent drives everything ──

    # Number-based quick replies only valid in fresh context
    _NUMBER_MAP = {"1": "study", "2": "job", "3": "news", "4": "planning"}
    msg_stripped = message.strip()
    if msg_stripped in _NUMBER_MAP:
        picked = _NUMBER_MAP[msg_stripped]
        state = build_initial_state(picked)
        update_user_state(user_id, state)
        handler = _FLOW_HANDLERS[picked]
        reply, state = handler(user_id, message, state)
        return {"reply": reply, "state": state}

    # Greeting: human reply, no data dump
    if intent == "greeting":
        state = build_initial_state("general")
        update_user_state(user_id, state)
        reply = _handle_greeting(user_id, message)
        return {"reply": reply, "state": state}

    # Emotion: empathize but push
    if intent == "emotion":
        state = build_initial_state("general")
        update_user_state(user_id, state)
        reply = _handle_emotion(user_id, message)
        return {"reply": reply, "state": state}

    # Study, job, news, planning: start the flow
    if intent in _FLOW_HANDLERS:
        state = build_initial_state(intent)
        update_user_state(user_id, state)
        handler = _FLOW_HANDLERS[intent]
        reply, state = handler(user_id, message, state)
        return {"reply": reply, "state": state}

    # Unclear: use mode as context hint
    if intent == "unclear":
        # Mode-aware fallback
        if mode_normalized in _FLOW_HANDLERS and mode_normalized != "general":
            state = build_initial_state(mode_normalized)
            update_user_state(user_id, state)
            handler = _FLOW_HANDLERS[mode_normalized]
            reply, state = handler(user_id, message, state)
            return {"reply": reply, "state": state}

        state = build_initial_state("general")
        update_user_state(user_id, state)
        reply = _handle_unclear(user_id, message, mode_normalized)
        return {"reply": reply, "state": state}

    # Should never reach here
    return {
        "reply": "What do you need? Study, jobs, news, or a daily plan?",
        "state": build_initial_state("general"),
    }
