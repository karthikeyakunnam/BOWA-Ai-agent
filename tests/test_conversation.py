"""Tests for conversation routing — detect_intent, mode routing, and analyze_user_state."""

import pytest

from services.conversation import (
    detect_intent,
    analyze_user_state,
    _looks_like,
    _select_action_from_reason,
    _is_too_similar,
    _render_without_llm,
)


# ---------------------------------------------------------------------------
# detect_intent — General mode (message-first detection)
# ---------------------------------------------------------------------------
class TestDetectIntentGeneral:
    """Intent detection when mode is General (default)."""

    def test_greeting(self):
        assert detect_intent("hi") == "greeting"
        assert detect_intent("hello") == "greeting"
        assert detect_intent("Hey") == "greeting"

    def test_jobs_from_message(self):
        assert detect_intent("show me jobs") == "jobs"
        assert detect_intent("find me an intern role") == "jobs"
        assert detect_intent("career options") == "jobs"

    def test_tracker_from_message(self):
        assert detect_intent("plan my day") == "tracker"
        assert detect_intent("schedule today") == "tracker"

    def test_news_from_message(self):
        assert detect_intent("show news") == "news"
        assert detect_intent("latest headlines") == "news"
        assert detect_intent("market update") == "news"

    def test_study_from_message(self):
        assert detect_intent("I want to study") == "study"
        assert detect_intent("learn python") == "study"
        assert detect_intent("CSE roadmap") == "study"

    def test_vague_message_defaults_general(self):
        assert detect_intent("hmm") == "general"
        assert detect_intent("ok") == "general"
        assert detect_intent("what") == "general"


# ---------------------------------------------------------------------------
# detect_intent — Mode-based detection (when message has no keywords)
# ---------------------------------------------------------------------------
class TestDetectIntentModes:
    """Intent detection when mode tab overrides a vague message."""

    def test_study_mode(self):
        assert detect_intent("tell me more", mode="Study") == "study"

    def test_jobs_mode(self):
        assert detect_intent("what next", mode="Jobs") == "jobs"

    def test_news_mode(self):
        assert detect_intent("anything new", mode="News") == "news"

    def test_tracker_mode(self):
        assert detect_intent("continue", mode="Tracker") == "tracker"

    def test_message_overrides_mode(self):
        """Explicit job keyword in message should win over Study mode."""
        assert detect_intent("show me jobs", mode="Study") == "jobs"

    def test_general_mode_fallback(self):
        assert detect_intent("hmm ok", mode="General") == "general"


# ---------------------------------------------------------------------------
# analyze_user_state — mood, clarity, urgency detection
# ---------------------------------------------------------------------------
class TestAnalyzeUserState:

    def test_lazy_mood(self):
        result = analyze_user_state("I don't feel like doing anything", None)
        assert result["mood"] == "lazy"

    def test_confused_mood(self):
        result = analyze_user_state("I don't understand what this is", None)
        assert result["mood"] == "confused"

    def test_focused_mood_with_goal(self):
        result = analyze_user_state("I want to become a data analyst", None)
        assert result["mood"] == "focused"
        assert result["clarity"] == "clear"

    def test_high_urgency(self):
        result = analyze_user_state("I need this right now", None)
        assert result["urgency"] == "high"

    def test_medium_urgency(self):
        result = analyze_user_state("I have to do this today", None)
        assert result["urgency"] == "medium"

    def test_low_urgency_default(self):
        result = analyze_user_state("maybe later", None)
        assert result["urgency"] == "low"

    def test_next_with_context_is_clear(self):
        state = {"last_action_result": {"type": "plan"}}
        result = analyze_user_state("next", state)
        assert result["clarity"] == "clear"

    def test_vague_input(self):
        result = analyze_user_state("hmm", None)
        assert result["clarity"] == "vague"


# ---------------------------------------------------------------------------
# _select_action_from_reason — deterministic action choice
# ---------------------------------------------------------------------------
class TestSelectAction:

    def test_lazy_mood_triggers_motivation(self):
        reason = {"mood": "lazy", "clarity": "clear", "intent": "general"}
        action = _select_action_from_reason(reason, None, "lazy today")
        assert action == "motivate_then_continue"

    def test_confused_mood_triggers_explanation(self):
        reason = {"mood": "confused", "clarity": "vague", "intent": "general"}
        action = _select_action_from_reason(reason, None, "what is this")
        assert action == "explain_then_continue"

    def test_vague_clarity_asks_clarification(self):
        reason = {"mood": "curious", "clarity": "vague", "intent": "general"}
        action = _select_action_from_reason(reason, None, "hmm")
        assert action == "ask_clarification"


# ---------------------------------------------------------------------------
# _is_too_similar — reply deduplication
# ---------------------------------------------------------------------------
class TestSimilarityCheck:

    def test_exact_match_is_similar(self):
        assert _is_too_similar("hello there", "hello there") is True

    def test_different_messages_not_similar(self):
        assert _is_too_similar("plan your day now", "show me jobs in AI") is False

    def test_empty_last_reply_not_similar(self):
        assert _is_too_similar("anything", "") is False

    def test_high_word_overlap_is_similar(self):
        reply = "You should start by learning the basics of SQL right now"
        last = "You should start by learning the basics of SQL today"
        assert _is_too_similar(reply, last) is True

    def test_short_messages_skip_overlap_check(self):
        assert _is_too_similar("ok", "ok") is True
        assert _is_too_similar("yes", "no") is False


# ---------------------------------------------------------------------------
# _render_without_llm — deterministic offline rendering
# ---------------------------------------------------------------------------
class TestRenderWithoutLLM:

    def test_renders_clarification(self):
        result = {
            "type": "clarification",
            "question": "What do you want?",
            "choices": ["study", "jobs"],
            "next_action": "Pick one.",
        }
        text = _render_without_llm(result)
        assert "What do you want?" in text
        assert "study" in text

    def test_renders_motivation(self):
        result = {
            "type": "motivation",
            "message": "Stop overthinking.",
            "next_action": "Start now.",
        }
        text = _render_without_llm(result)
        assert "Stop overthinking." in text

    def test_renders_news_empty(self):
        result = {"type": "news", "list": [], "next_action": "configure"}
        text = _render_without_llm(result)
        assert "No live news" in text

    def test_renders_plan_step(self):
        result = {
            "type": "plan",
            "goal": "learn SQL",
            "steps": [{"duration_minutes": 30, "task": "SELECT basics"}],
            "next_action": "Start now.",
        }
        text = _render_without_llm(result)
        assert "learn SQL" in text
        assert "SELECT basics" in text
