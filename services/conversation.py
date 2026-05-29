"""Decision-driven conversation engine for BOWA.

Flow:
User -> detect intent -> decide action -> execute action -> render response.

The LLM never controls logic. It only converts structured action results into
sharp BOWA-style language.
"""

import json
import logging
import random
import threading
import time
from typing import Any, Generator

from services.actions import (
    CONTINUE_FLOW,
    EXPLAIN_THEN_CONTINUE,
    MOTIVATE_THEN_CONTINUE,
    decide_action,
    execute_action,
)
from services.execution import (
    check_expired_sessions,
    end_execution_session,
    get_execution_session,
    start_execution_session,
    create_one_session_task,
)
from services.news_feedback import capture_user_reaction
from services.daily_plan import generate_daily_plan
from services.memory import load_user_memory, save_user_memory
from services.personality import adapt_message
from services.formatter import format_response
from services.llm import generate_response, llm_available, _generate_chat_response
from services.response_builder import build_response
from services.action_selector import decide_next_action
from services.planner_engine import generate_plan
from services.state import build_initial_state, get_user_state, update_user_state
from services.trajectory import load_trajectory, update_trajectory
from services.vector_memory import add_memory, retrieve_memory, get_relevant_memory
from services.reflection import analyze_performance
from services.strategy import choose_strategy
from services.proactive import _update_news_escalation_count


logger = logging.getLogger(__name__)

user_locks: dict[str, threading.Lock] = {}
user_locks_lock = threading.Lock()


def _get_conversation_history(user_id: str) -> list[dict[str, Any]]:
    """Retrieve short-term conversation history from state.json."""
    state = get_user_state(user_id)
    if not state or "history" not in state:
        return []
    history = state["history"]
    return history if isinstance(history, list) else []


def _save_conversation_history(user_id: str, history: list[dict[str, Any]]) -> None:
    """Save compact short-term conversation history without resetting state."""
    state = get_user_state(user_id) or build_initial_state("general")
    state["history"] = history[-10:]
    update_user_state(user_id, state)


def _looks_like(text: str, keywords: list[str]) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in keywords)


def detect_intent(message: str, mode: str = "General") -> str:
    """Detect intent from message first, with mode as a weak hint."""
    lowered = message.lower().strip()

    if lowered in {"hi", "hello", "hey", "yo", "sup", "greetings", "hi bowa", "hello bowa", "hey bowa"} or any(lowered.startswith(g + " ") for g in {"hi", "hello", "hey", "yo", "sup"}):
        return "greeting"

    if _looks_like(lowered, ["job", "jobs", "intern", "career", "hiring", "role"]):
        return "jobs"
    if _looks_like(lowered, ["plan my day", "plan today", "tracker", "schedule today"]):
        return "tracker"
    if _looks_like(lowered, ["news", "latest", "headline", "market update"]):
        return "news"
    if _looks_like(lowered, ["study", "roadmap", "learn", "prepare", "cse", "ece"]):
        return "study"

    mode_map = {
        "Jobs": "jobs",
        "Tracker": "tracker",
        "News": "news",
        "Study": "study",
    }
    return mode_map.get(mode, "general")


def analyze_user_state(message: str, state: dict[str, Any] | None) -> dict[str, str]:
    """Reason about user state before choosing an action."""
    lowered = message.lower().strip()
    intent = detect_intent(message)

    lazy_markers = ["don't feel", "dont feel", "lazy", "tired", "exhausted", "no energy"]
    confused_markers = ["what is this", "what's this", "confused", "i don't understand", "dont understand"]
    urgency_markers = ["urgent", "today", "now", "deadline", "asap", "tomorrow"]
    clear_goal_markers = ["i want", "i need", "my goal", "become", "learn", "build", "prepare", "plan my day"]

    if _looks_like(lowered, lazy_markers):
        mood = "lazy"
    elif _looks_like(lowered, confused_markers):
        mood = "confused"
    elif _looks_like(lowered, clear_goal_markers) or intent in {"jobs", "study", "tracker", "news"}:
        mood = "focused"
    else:
        mood = "curious"

    if _looks_like(lowered, clear_goal_markers) or intent in {"jobs", "study", "tracker", "news"} or lowered == "next":
        clarity = "clear"
    else:
        clarity = "vague"

    if _looks_like(lowered, ["urgent", "asap", "deadline", "right now"]):
        urgency = "high"
    elif _looks_like(lowered, urgency_markers):
        urgency = "medium"
    else:
        urgency = "low"

    if state and state.get("last_action_result") and lowered in {"next", "continue", "ok", "done"}:
        clarity = "clear"
        mood = "focused" if mood != "lazy" else mood

    return {
        "intent": intent,
        "mood": mood,
        "clarity": clarity,
        "urgency": urgency,
    }


def _select_action_from_reason(
    reason: dict[str, str],
    state: dict[str, Any] | None,
    message: str,
    trajectory: dict[str, Any] | None = None,
) -> str:
    """Let reasoning steer the deterministic action choice."""
    if reason["mood"] == "lazy":
        return MOTIVATE_THEN_CONTINUE
    if reason["mood"] == "confused":
        return EXPLAIN_THEN_CONTINUE
    if reason["clarity"] == "vague":
        return "ask_clarification"
    return decide_action(reason["intent"], state, message, trajectory)


def _trajectory_context_lines(action_result: dict[str, Any]) -> list[str]:
    """Return response context from trajectory."""
    trajectory = action_result.get("trajectory")
    if not isinstance(trajectory, dict):
        return []

    stage = trajectory.get("current_stage", "unclear")
    score = trajectory.get("consistency_score", 0)
    feedback = trajectory.get("feedback", "")
    stage_labels = {
        "unclear": "You're in unclear phase.",
        "planning": "You're in planning phase.",
        "executing": "You're in execution phase.",
        "consistent": "You're building consistency.",
        "advanced": "You're ready for harder work.",
    }

    lines = [stage_labels.get(stage, "You're in progress.")]
    if feedback:
        lines.append(feedback)
    lines.append(f"Consistency: {score}/100")
    return lines


def _render_without_llm(action_result: dict[str, Any]) -> str:
    """Deterministic renderer for offline mode."""
    result_type = action_result.get("type")
    context_lines = _trajectory_context_lines(action_result)

    if result_type == "clarification":
        choices = ", ".join(action_result.get("choices", []))
        return "\n".join([
            *context_lines,
            f"{action_result.get('question')}",
            f"Pick one: {choices}.",
        ])

    if result_type == "motivation":
        return "\n".join([
            *context_lines,
            action_result.get("message", "Stop overthinking. Start small."),
            f"Next: {action_result.get('next_action')}",
        ])

    if result_type == "explanation":
        return "\n".join([
            *context_lines,
            action_result.get("message", "I am using your context to pick the next action."),
            f"Next: {action_result.get('next_action')}",
        ])

    if result_type == "jobs":
        lines = [*context_lines, f"Target role: **{action_result.get('target_role')}**"]
        for job in action_result.get("list", [])[:3]:
            lines.append(f"- {job.get('role')} at {job.get('company')} ({job.get('location')})")
        missing = action_result.get("skill_gap", {}).get("missing_skills", [])
        if missing:
            lines.append(f"Next skill: **{missing[0]}**")
        lines.append(f"Next: {action_result.get('next_action')}")
        return "\n".join(lines)

    if result_type == "news":
        news = action_result.get("list", [])
        if not news:
            return "\n".join([
                *context_lines,
                "No live news configured.",
                "Next: add `NEWS_API_KEY` or ask for jobs, study, or planning.",
            ])
        lines = [*context_lines, "Priority news:"]
        for item in news[:3]:
            lines.append(f"- [{item.get('priority')}] {item.get('title')}")
        lines.append(f"Next: {action_result.get('next_action')}")
        return "\n".join(lines)

    if result_type == "tracker":
        plan = action_result.get("plan", {})
        lines = [*context_lines, f"Plan: **{plan.get('goal')}**"]
        for block in plan.get("blocks", [])[:4]:
            lines.append(f"- {block.get('duration_minutes')} min: {block.get('task')}")
        lines.append(f"Start: {action_result.get('next_action')}")
        return "\n".join(lines)

    if result_type == "plan":
        lines = [*context_lines, f"Goal: **{action_result.get('goal')}**"]
        for step in action_result.get("steps", [])[:4]:
            lines.append(f"- {step.get('duration_minutes')} min: {step.get('task')}")
        lines.append(f"Start: {action_result.get('next_action')}")
        return "\n".join(lines)

    lines = [*context_lines, "Continue from where you stopped."]
    lines.append(f"Do next: {action_result.get('next_action')}")
    return "\n".join(lines)


def _render_with_llm(
    action_result: dict[str, Any],
    state: dict[str, Any] | None,
    semantic_context: list[str],
) -> str:
    """Use LLM only to convert structured action data into human response."""
    deterministic_reply = _render_without_llm(action_result)
    llm_reply = generate_response(
        context={
            "state": state or {},
            "semantic_context": semantic_context[:3],
            "action_type": action_result.get("type"),
        },
        structured_data=deterministic_reply,
    )
    return llm_reply or deterministic_reply


def _handle_news_action(user_id: str, action: str, news_content: str, goal: str, urgency: str) -> dict[str, Any]:
    """Handle news action: act, watch, or ignore."""
    import random
    
    # Determine category from news content
    category = "General"
    content_lower = news_content.lower()
    if any(word in content_lower for word in ["ai", "machine learning", "tech", "software"]):
        category = "AI"
    elif any(word in content_lower for word in ["job", "hiring", "career", "layoff"]):
        category = "Jobs"
    elif any(word in content_lower for word in ["finance", "market", "economy", "stock"]):
        category = "Finance"
    
    if action == "act":
        # Create execution task with 15-30 min duration
        duration = random.randint(15, 30)
        task = f"Act on news: {news_content[:100]}..."
        
        # Prevent duplicate sessions
        existing = get_execution_session(user_id)
        if existing and existing.get("active") and existing.get("status") == "running":
            return {"action": "act", "status": "duplicate", "task": existing.get("task"), "duration": existing.get("duration")}
        
        # Generate news_id from content hash for tracking
        import hashlib
        news_id = hashlib.md5(news_content.encode()).hexdigest()[:8]
        
        session = create_one_session_task(user_id, task, duration, source_type="news", news_id=news_id, category=category)
        
        # Capture user reaction for feedback tracking
        capture_user_reaction(
            user_id=user_id,
            news_title=news_content[:100],
            category=category,
            action_suggested=action,
            user_action="acted",
            goal=goal
        )
        
        # Reset escalation count when user takes action
        _update_news_escalation_count(user_id, False)
        
        return {"action": "act", "status": "created", "task": task, "duration": duration}
    
    elif action == "watch":
        # Store as tracked item only
        memory = load_user_memory(user_id) or {}
        if "watch_list" not in memory:
            memory["watch_list"] = []
        
        # Deduplicate by content
        existing_contents = {item.get("content", "")[:200] for item in memory["watch_list"]}
        if news_content[:200] in existing_contents:
            return {"action": "watch", "status": "duplicate", "item": {"content": news_content[:200]}}
        
        watch_item = {
            "content": news_content[:200],
            "category": category,
            "urgency": urgency,
            "timestamp": time.time(),
            "goal": goal
        }
        memory["watch_list"].append(watch_item)
        # Cap at 20 items
        memory["watch_list"] = memory["watch_list"][-20:]
        save_user_memory(user_id, memory)
        
        # Capture user reaction for feedback tracking
        capture_user_reaction(
            user_id=user_id,
            news_title=news_content[:100],
            category=category,
            action_suggested=action,
            user_action="watched",
            goal=goal
        )
        
        return {"action": "watch", "status": "tracked", "item": watch_item}
    
    elif action == "ignore":
        # Log and skip
        memory = load_user_memory(user_id) or {}
        if "ignored_news" not in memory:
            memory["ignored_news"] = []
        
        ignored_item = {
            "content": news_content[:200],
            "category": category,
            "urgency": urgency,
            "timestamp": time.time(),
            "reason": "not_relevant"
        }
        memory["ignored_news"].append(ignored_item)
        save_user_memory(user_id, memory)
        
        # Capture user reaction for feedback tracking
        capture_user_reaction(
            user_id=user_id,
            news_title=news_content[:100],
            category=category,
            action_suggested=action,
            user_action="ignored",
            goal=goal
        )
        
        return {"action": "ignore", "status": "skipped", "item": ignored_item}
    
    return {"action": "unknown", "status": "error"}


def _is_too_similar(reply: str, last_reply: str) -> bool:
    """Lightweight similarity check - returns True if replies are too similar."""
    if not last_reply:
        return False
    
    # Exact match
    if reply.strip() == last_reply.strip():
        return True
    
    # Simple similarity: check if most words are the same
    reply_words = set(reply.lower().split())
    last_words = set(last_reply.lower().split())
    
    # If both have more than 5 words and >80% overlap
    if len(reply_words) > 5 and len(last_words) > 5:
        overlap = len(reply_words & last_words)
        similarity = overlap / max(len(reply_words), len(last_words))
        if similarity > 0.8:
            return True
    
    return False


def _regenerate_reply_if_similar(
    reply: str, 
    user_id: str, 
    message: str, 
    state: dict[str, Any] | None,
    action_result: dict[str, Any]
) -> str:
    """Regenerate reply if too similar to last reply, with fallback."""
    state = state or {}
    last_reply = state.get("last_reply", "")
    
    # First check similarity
    if not _is_too_similar(reply, last_reply):
        return reply
    
    # Try to regenerate once
    try:
        # Get a different action result if possible
        if action_result.get("type") in ["clarification", "motivation", "explanation"]:
            fallback_result = {
                "type": "clarification",
                "question": "Be specific. What exactly do you want next?",
                "choices": ["generate plan", "show jobs", "show news", "create tracker"],
                "next_action": "Give me one clear target.",
            }
            regenerated = _render_without_llm(fallback_result)
            if not _is_too_similar(regenerated, last_reply):
                return format_response(regenerated)
    except Exception:
        pass
    
    # If still similar, return fallback message
    return "Give a specific input so I can move forward."


def _avoid_repeat(reply: str, history: list[dict[str, Any]], action_result: dict[str, Any]) -> str:
    """Ensure BOWA never returns the exact same message twice."""
    previous_replies = [
        item.get("content", "")
        for item in history
        if item.get("role") == "assistant"
    ]
    if reply not in previous_replies:
        return reply

    next_action = action_result.get("next_action") or "Give me the result of your last step."
    return format_response(
        f"Same context, next move changes.\nNext: {next_action}\nDo it, then report back with what happened."
    )


def handle_unclear_input(
    message: str,
    state: dict[str, Any] | None,
    user_id: str,
) -> dict[str, Any]:
    """Fallback handler for loops, vague input, and context questions."""
    lowered = message.lower().strip()

    if lowered == "next":
        return execute_action(CONTINUE_FLOW, user_id, message, state)

    if lowered in {"what is this", "what's this", "what are you doing"}:
        previous = state.get("last_action_result") if state else None
        previous_type = previous.get("type") if isinstance(previous, dict) else "conversation"
        result = {
            "type": "clarification",
            "question": (
                f"You are in the {previous_type} flow. "
                "I am trying to define your next concrete step."
            ),
            "choices": ["say next", "give goal", "ask jobs", "plan my day"],
            "next_action": "Reply with `next` or give me the exact thing you want.",
        }
        _save_fallback_state(user_id, state, result)
        return result

    result = {
        "type": "clarification",
        "question": "Be specific. What exactly do you want next?",
        "choices": ["generate plan", "show jobs", "show news", "create tracker"],
        "next_action": "Give me one clear target.",
    }
    _save_fallback_state(user_id, state, result)
    return result


def _save_fallback_state(
    user_id: str,
    state: dict[str, Any] | None,
    action_result: dict[str, Any],
) -> None:
    next_state = state or build_initial_state("general")
    current_stage = next_state.get("stage")
    next_state["stage"] = "clarified" if current_stage == "ask" else "ask"
    next_state["last_action"] = action_result["type"]
    next_state["last_action_result"] = action_result
    update_user_state(user_id, next_state)


def _set_last_reply(user_id: str, reply: str) -> dict[str, Any]:
    """Persist last reply for loop detection."""
    state = get_user_state(user_id) or build_initial_state("general")
    state["last_reply"] = reply
    return update_user_state(user_id, state)


def _force_stage_progress(user_id: str, previous_stage: str | None) -> None:
    """Guarantee each turn changes the stage marker."""
    state = get_user_state(user_id) or build_initial_state("general")
    current_stage = state.get("stage")
    if current_stage != previous_stage:
        return

    progress_count = int(state.get("progress_count", 0)) + 1
    state["progress_count"] = progress_count

    if current_stage == "ask":
        state["stage"] = "clarified"
    elif current_stage == "clarified":
        state["stage"] = "planned"
    elif current_stage == "planned":
        state["stage"] = "executing"
    elif current_stage == "executing" or str(current_stage).startswith("executing_"):
        state["stage"] = f"executing_{progress_count}"
    else:
        state["stage"] = "ask"

    update_user_state(user_id, state)


def handle_user_message(
    user_id: str,
    message: str,
    mode: str = "General",
) -> dict[str, Any]:
    """Process one BOWA turn through the Action Engine."""
    if not user_id:
        user_id = "default"

    from event_timeline import append_event
    append_event(user_id, "message_received", {"message": message, "mode": mode})

    with user_locks_lock:
        lock = user_locks.get(user_id)
        if lock is None:
            lock = threading.Lock()
            user_locks[user_id] = lock

    logger.info("bowa_lock acquired user=%s", user_id)
    lock.acquire()
    try:
        memory = load_user_memory(user_id) or {}
        last_goal = memory.get("last_goal")
        last_topic = memory.get("last_topic")
        intent = detect_intent(message, mode)

        if last_goal and intent in ["study", "tracker"] and last_goal not in message.lower():
            message = f"You were working on {last_goal} earlier. {message}"

        if last_goal and not memory.get("daily_plan"):
            plan = generate_daily_plan(user_id)
            memory["daily_plan"] = plan
            save_user_memory(user_id, memory)

        lowered = message.lower().strip()
        reason_check = None
        if last_goal:
            reason_check = analyze_user_state(message, get_user_state(user_id))
            if reason_check["clarity"] == "vague" and lowered in {"hmm", "uh", "okay", "ok", "maybe", "not sure", "still thinking"}:
                reply = f"You're here to move toward your goal: {last_goal}. Let's continue your plan now."
                reply = adapt_message(reply, user_id)
                return {"reply": reply, "action": "continue", "reason": "goal_continuation", "state": get_user_state(user_id), "structured": {}}

        # Check for execution follow-up
        session = get_execution_session(user_id)
        if session and session.get("task"):
            if session.get("status") == "expired":
                lowered = message.lower().strip()
                if lowered in ["yes", "y", "completed", "done"]:
                    end_execution_session(user_id, True)
                    reply = "Great! Consistency boosted. What's next?"
                elif lowered in ["no", "n", "not yet", "failed"]:
                    end_execution_session(user_id, False)
                    reply = "Okay, let's break it down. Start with 10 minutes."
                else:
                    reply = "Did you complete the task? Reply 'yes' or 'no'."
                reply = adapt_message(reply, user_id)
                return {"reply": reply, "action": "execution_followup", "reason": "execution_followup", "state": get_user_state(user_id), "structured": {}}

        # Check for watch list prompt responses
        if lowered in ["act", "ignore"]:
            memory = load_user_memory(user_id) or {}
            watch_list = memory.get("watch_list", [])
            
            # Find the oldest prompted watch item
            prompted_items = [item for item in watch_list if item.get("prompted", False)]
            
            if prompted_items:
                oldest_item = min(prompted_items, key=lambda x: x.get("timestamp", 0))
                
                if lowered == "act":
                    # Create execution task from watch item
                    duration = random.randint(15, 30)
                    task = f"Act on watched item: {oldest_item.get('content', '')[:100]}..."
                    
                    # Prevent duplicate sessions
                    existing = get_execution_session(user_id)
                    if not (existing and existing.get("active") and existing.get("status") == "running"):
                        # Generate watch_id from content hash for tracking
                        import hashlib
                        watch_id = hashlib.md5(oldest_item.get('content', '').encode()).hexdigest()[:8]
                        
                        session = create_one_session_task(user_id, task, duration, source_type="watch", news_id=watch_id, category=oldest_item.get("category", "General"))
                        reply = f"✅ Task created: {task} - {duration}min session started."
                        
                        # Track as conversion from watch to act
                        capture_user_reaction(
                            user_id=user_id,
                            news_title=oldest_item.get("content", "")[:100],
                            category=oldest_item.get("category", "General"),
                            action_suggested="watch",
                            user_action="acted",
                            goal=oldest_item.get("goal", "")
                        )
                    else:
                        reply = "Already have an active session. Complete it first."
                    
                elif lowered == "ignore":
                    # Remove from watch list
                    watch_list.remove(oldest_item)
                    memory["watch_list"] = watch_list
                    save_user_memory(user_id, memory)
                    
                    reply = "🗑️ Watched item removed."
                    
                    # Track as ignored
                    capture_user_reaction(
                        user_id=user_id,
                        news_title=oldest_item.get("content", "")[:100],
                        category=oldest_item.get("category", "General"),
                        action_suggested="watch",
                        user_action="ignored",
                        goal=oldest_item.get("goal", "")
                    )
                
                reply = adapt_message(reply, user_id)
                return {"reply": reply, "action": "watch_list_response", "reason": "watch_list_action", "state": get_user_state(user_id), "structured": {}}

        state = get_user_state(user_id, mode) or build_initial_state(mode)
        if state.get("mode") != mode:
            state["mode"] = mode
            update_user_state(user_id, state)
        previous_stage = state.get("stage") if state else None
        history = _get_conversation_history(user_id)
        semantic_context = get_relevant_memory(user_id, message)
        trajectory = load_trajectory(user_id)
        state_for_reason = {**(state or {}), "user_id": user_id, "trajectory": trajectory}
        
        last_action = state_for_reason.get("last_action", "none")
        reflection = analyze_performance(state_for_reason, last_action, message)
        state_for_reason["reflection"] = reflection

        strategy_data = choose_strategy(state_for_reason, reflection, intent)

        memory = load_user_memory(user_id) or {}
        memory["last_reflection"] = reflection
        memory["last_strategy"] = strategy_data
        save_user_memory(user_id, memory)

        plan = generate_plan(state_for_reason, intent, message)
        if plan:
            state_for_reason["active_plan"] = plan
            update_user_state(user_id, state_for_reason)
            logger.info("bowa_plan steps=%d current=%d", plan["total_steps"], plan["current_step"])

        reason = analyze_user_state(message, state_for_reason)
        
        if lowered.startswith("explain this news and what i should do:") or "news" in intent:
            news_content = message
            if ":" in message:
                news_content = message[message.index(":") + 1:].strip()
            
            goal = state_for_reason.get("goal", "improve my skills")
            
            # Determine urgency based on content and goal
            urgency = "low"
            nc_lower = news_content.lower()
            if any(word in nc_lower for word in ["job", "layoff", "hiring", "market", "economy", "crash"]):
                urgency = "high"
            elif any(word in nc_lower for word in ["update", "launch", "new", "ai", "tech"]):
                urgency = "medium"
            
            # Enhanced prompt with structured output format
            prompt = f"""You are BOWA - a personalized intelligence system. Explain this news for the user.

News: {news_content}
User Goal: {goal}

Provide your response in this EXACT 4-part structure:

1. **What happened** (simple 1-2 sentences)
2. **Why it matters globally** (broader context)
3. **Why it matters for YOU** (specific to their goal: {goal})
4. **Action**: Choose one → ignore / watch / act

After all 4 sections, END with this exact format:
Next: Do this → {{specific actionable step for this week}}
"""
            
            messages = [{"role": "system", "content": prompt}]
            resp = _generate_chat_response(messages)
            raw_reply = resp.get("content", "")
            
            # Ensure follow-up suggestion is present
            if "Next: Do this" not in raw_reply and "Next:" not in raw_reply:
                raw_reply += f"\n\nNext: Do this → Review similar news in your field weekly"
            
            # Extract action from LLM response
            action = "ignore"  # default
            if "Action: act" in raw_reply.lower():
                action = "act"
            elif "Action: watch" in raw_reply.lower():
                action = "watch"
            elif "Action: ignore" in raw_reply.lower():
                action = "ignore"
            
            # Handle the extracted action
            action_result = _handle_news_action(user_id, action, news_content, goal, urgency)
            
            formatted_reply = format_response(f"📰 **Urgency: {urgency.upper()}**\n\n{raw_reply}")
            
            # Add action confirmation to reply
            if action == "act":
                formatted_reply += f"\n\n✅ **Action Started**: {action_result.get('task', 'Task created')} - {action_result.get('duration', 25)}min session"
            elif action == "watch":
                formatted_reply += "\n\n👁️ **Added to Watch List** - Will monitor for updates"
            elif action == "ignore":
                formatted_reply += "\n\n⏭️ **Skipped** - Not relevant to current goals"
            
            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": formatted_reply})
            _save_conversation_history(user_id, history)
            _set_last_reply(user_id, formatted_reply)
            return {"reply": formatted_reply, "action": "news_explain", "urgency": urgency, "news_action": action, "reason": reason, "state": get_user_state(user_id), "structured": action_result}

        if lowered in ["what is the task", "what is my task", "what task", "what's the task", "what's my task"]:
            session = get_execution_session(user_id)
            if session and session.get("task"):
                reply = f"Current active task: {session.get('task')}."
            elif state_for_reason.get("active_plan") and not state_for_reason["active_plan"].get("completed"):
                plan = state_for_reason["active_plan"]
                current_idx = plan.get("current_step", 1) - 1
                steps = plan.get("steps", [])
                if 0 <= current_idx < len(steps):
                    step = steps[current_idx]
                    reply = f"Current plan step: {step.get('action') or step.get('task')}"
                else:
                    reply = "You're in a plan, but I couldn't find the exact step."
            else:
                reply = "No active task. Choose: study, jobs, or plan your day."
            
            formatted_reply = format_response(reply)
            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": formatted_reply})
            _save_conversation_history(user_id, history)
            _set_last_reply(user_id, formatted_reply)
            return {"reply": formatted_reply, "action": "clarification", "reason": reason, "state": get_user_state(user_id), "structured": {}}

        # Smart Mode Routing
        mode_lower = mode.lower()
        intent_from_msg = reason["intent"]
        
        if intent_from_msg == "greeting":
            reason["intent"] = "greeting"
        elif mode_lower == "tracker":
            reason["intent"] = "tracker"
        elif mode_lower == "general":
            pass # Keep intent_from_msg
        else:
            if intent_from_msg in ["tracker", "study", "jobs", "news"]:
                priorities = {"tracker": 5, "study": 4, "jobs": 3, "news": 2, "general": 1}
                if priorities.get(intent_from_msg, 1) > priorities.get(mode_lower, 1):
                    reason["intent"] = intent_from_msg
                else:
                    reason["intent"] = mode_lower
            else:
                reason["intent"] = mode_lower
                
        if reason["intent"] != "general":
            reason["clarity"] = "clear"
            reason["mood"] = "focused"
            
        intent = reason["intent"]
        if lowered in {"what is this", "what's this", "what are you doing"}:
            action = EXPLAIN_THEN_CONTINUE
            action_result = execute_action(action, user_id, message, state_for_reason)
        else:
            if state_for_reason.get("active_plan") and not state_for_reason["active_plan"].get("completed"):
                action = "execute_plan_step"
            else:
                action = _select_action_from_reason(reason, state_for_reason, message, trajectory)
            action_result = execute_action(action, user_id, message, state_for_reason)

        if action == "execute_plan_step":
            plan = state_for_reason.get("active_plan") or {}
            current_index = max(0, min(plan.get("current_step", 1) - 1, len(plan.get("steps", [])) - 1))
            current_step = plan.get("steps", [])[current_index] if plan.get("steps") else {}
            action_result = {
                "type": "plan_step",
                "message": f"Step {plan.get('current_step', 1)}: {current_step.get('action', 'Continue with your plan')}",
                "next_action": "Do this step now, then tell me what you finished.",
                "plan_step": plan.get("current_step", 1),
                "total_steps": plan.get("total_steps", len(plan.get("steps", [])))
            }

        trajectory = update_trajectory({**(get_user_state(user_id) or {}), "user_id": user_id}, action_result)
        action_result["trajectory"] = trajectory
        state_after_trajectory = get_user_state(user_id) or build_initial_state("general")
        state_after_trajectory["trajectory"] = trajectory
        update_user_state(user_id, state_after_trajectory)

        # Log the selected action for observability only — do not override primary action.
        # The primary action at lines 791-795 already considers mood, clarity, and intent.
        # Overriding here caused action flips (e.g., user asks for jobs but gets motivation).
        selected_action = decide_next_action(state_after_trajectory, intent, {"user_message": message})
        logger.info("bowa_action_selector action=%s intent=%s (advisory only)", selected_action, intent)

        if llm_available():
            deterministic_reply = _render_without_llm(action_result)
            memory = load_user_memory(user_id) or {}
            reward = memory.get("last_reward")
            streak = memory.get("current_streak", 0)
            structured_data = build_response(state_after_trajectory, intent, deterministic_reply, strategy_data, reflection, reward, streak)
            structured_data["action"] = selected_action
            logger.info(
                "bowa_structured stage=%s tone=%s next=%s",
                structured_data.get("stage"),
                structured_data.get("tone"),
                structured_data.get("next_step"),
            )
            raw_reply = generate_response(
                context=state_after_trajectory,
                structured_data=structured_data,
            )
        else:
            raw_reply = _render_without_llm(action_result)

        reply = format_response(raw_reply)
        if llm_available():
            logger.info("bowa_llm intent=%s tools=groq reply=%s", intent, reply)

        # Prevent similar replies with regeneration
        latest_state = get_user_state(user_id) or state
        reply = _regenerate_reply_if_similar(reply, user_id, message, latest_state, action_result)
        if latest_state and reply == latest_state.get("last_reply"):
            action_result = handle_unclear_input(message, latest_state, user_id)
            if llm_available():
                raw_reply = _render_with_llm(action_result, latest_state, semantic_context)
            else:
                raw_reply = _render_without_llm(action_result)
            reply = format_response(raw_reply)

        reply = _avoid_repeat(reply, history, action_result)
        if latest_state and reply == latest_state.get("last_reply"):
            action_result = handle_unclear_input("vague", latest_state, user_id)
            reply = format_response(_render_without_llm(action_result))
            
        # Task 6: Prevent Repetition Strict Check
        if history and len(history) >= 2:
            last_assistant_msg = next((msg["content"] for msg in reversed(history) if msg["role"] == "assistant"), None)
            if last_assistant_msg and reply.strip() == last_assistant_msg.strip():
                reply = "I need more specific details to continue. Tell me exactly what you want to do."

        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": reply})
        _save_conversation_history(user_id, history)
        _set_last_reply(user_id, reply)
        _force_stage_progress(user_id, previous_stage)

        add_memory(user_id, message, role="user")
        add_memory(user_id, reply, role="assistant")

        # Update interaction count for personality
        memory = load_user_memory(user_id) or {}
        memory["interaction_count"] = memory.get("interaction_count", 0) + 1
        memory["last_topic"] = intent
        if "become" in message.lower() or "goal" in message.lower():
            # Simple extraction
            words = message.split()
            for i, word in enumerate(words):
                if word.lower() in ["become", "goal"]:
                    memory["last_goal"] = " ".join(words[i+1:i+4])  # next few words
                    break
        save_user_memory(user_id, memory)

        logger.info(
            "bowa_reason=%s action=%s trajectory_stage=%s consistency_score=%s final_reply=%r",
            reason,
            action,
            trajectory.get("current_stage"),
            trajectory.get("consistency_score"),
            reply,
        )

        # NOTE (FIX-1): Removed unconditional execution trigger that was here.
        # It created duplicate sessions on keyword match ("start", "do it", etc.)
        # after the action engine already handled the message.

        reply = adapt_message(reply, user_id)

        now = time.time()
        last_response_time = state_after_trajectory.get("last_response_time", 0)
        last_response_text = state_after_trajectory.get("last_response_text", "")
        if reply == last_response_text and now - last_response_time < 1.0:
            reply = "I heard you. Let's keep going with the next step."

        state_after_trajectory["last_response_time"] = time.time()
        state_after_trajectory["last_response_text"] = reply
        update_user_state(user_id, state_after_trajectory)

        time.sleep(random.uniform(0.3, 0.7))

        return {
            "reply": reply,
            "action": action_result.get("type", action),
            "reason": reason,
            "state": get_user_state(user_id),
            "structured": action_result,
        }
    finally:
        lock.release()
        logger.info("bowa_lock released user=%s", user_id)


def handle_user_message_stream(
    user_id: str,
    message: str,
    mode: str = "General",
) -> Generator[str, None, None]:
    """Stream a completed Action Engine response in small chunks."""
    result = handle_user_message(user_id, message, mode)
    reply = result["reply"]
    for index in range(0, len(reply), 24):
        yield reply[index:index + 24]
