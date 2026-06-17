"""Unit tests for BOWA Shallow Intelligence Fixes.

Covers:
1. Conversation History Injection
2. Strategy Injection
3. Returning User Greetings
4. News Classification Quality
5. Clarification State Machine
"""

import pytest
from unittest.mock import MagicMock, patch
from services.actions import execute_action
from services.llm import generate_response
from services.news_service import classify_news, assign_priority


# ---------------------------------------------------------------------------
# FIX 1 & 2: Conversation History & Strategy Injection
# ---------------------------------------------------------------------------

@patch("services.llm._get_client")
def test_llm_receives_conversation_history(mock_get_client):
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Mock LLM reply"
    mock_client.chat.completions.create.return_value.choices = [mock_choice]
    mock_get_client.return_value = mock_client

    history = [
        {"role": "user", "content": "Hello BOWA"},
        {"role": "assistant", "content": "Hello! What can I help you with?"},
    ]
    context = {
        "state": {
            "history": history
        }
    }
    generate_response(context, "Start now.")

    assert mock_client.chat.completions.create.called
    kwargs = mock_client.chat.completions.create.call_args[1]
    messages = kwargs["messages"]
    
    # Verify system prompt is present
    assert messages[0]["role"] == "system"
    # Verify history is injected in sequence
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "Hello BOWA"
    assert messages[2]["role"] == "assistant"
    assert messages[2]["content"] == "Hello! What can I help you with?"


@patch("services.llm._get_client")
def test_history_limited_to_10_messages(mock_get_client):
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Mock LLM reply"
    mock_client.chat.completions.create.return_value.choices = [mock_choice]
    mock_get_client.return_value = mock_client

    # 12 messages in history
    history = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}"} for i in range(12)]
    context = {
        "state": {
            "history": history
        }
    }
    generate_response(context, "Start now.")

    assert mock_client.chat.completions.create.called
    kwargs = mock_client.chat.completions.create.call_args[1]
    messages = kwargs["messages"]

    # History messages should be capped at the last 10 messages (msg 2 to msg 11)
    # The first message (messages[0]) is system prompt
    # The next 10 messages are the injected history
    injected_history = messages[1:11]
    assert len(injected_history) == 10
    assert injected_history[0]["content"] == "msg 2"
    assert injected_history[-1]["content"] == "msg 11"


@patch("services.llm._get_client")
def test_strategy_passed_to_llm(mock_get_client):
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Mock LLM reply"
    mock_client.chat.completions.create.return_value.choices = [mock_choice]
    mock_get_client.return_value = mock_client

    context = {
        "strategy": "simplify"
    }
    generate_response(context, "Start now.")

    assert mock_client.chat.completions.create.called
    kwargs = mock_client.chat.completions.create.call_args[1]
    messages = kwargs["messages"]
    
    # Check that "Strategy: simplify" and the simplify instruction are present
    found = False
    for msg in messages:
        if msg["role"] == "system" and "Strategy: simplify" in msg["content"]:
            assert "Reduce complexity." in msg["content"]
            found = True
            break
    assert found


@patch("services.llm._get_client")
def test_push_strategy_changes_prompt(mock_get_client):
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Mock LLM reply"
    mock_client.chat.completions.create.return_value.choices = [mock_choice]
    mock_get_client.return_value = mock_client

    context = {
        "strategy": "push"
    }
    generate_response(context, "Start now.")

    assert mock_client.chat.completions.create.called
    kwargs = mock_client.chat.completions.create.call_args[1]
    messages = kwargs["messages"]
    
    # Check that "Strategy: push" and the push instruction are present
    found = False
    for msg in messages:
        if msg["role"] == "system" and "Strategy: push" in msg["content"]:
            assert "Increase urgency." in msg["content"]
            found = True
            break
    assert found


# ---------------------------------------------------------------------------
# FIX 3: Returning User Greetings
# ---------------------------------------------------------------------------

def test_new_user_greeting(clean_memory, clean_state, user_id):
    clean_memory({})
    state = {
        "mode": "General",
        "clarification_pending": False,
        "clarification_count": 0,
    }
    clean_state(state)

    result = execute_action("ask_clarification", user_id, "hello", state)
    
    assert result["type"] == "clarification"
    assert result["question"] == "Tell me what you're trying to achieve."
    assert "study" in result["choices"]
    assert state["clarification_pending"] is True
    assert state["clarification_count"] == 1


def test_returning_user_greeting(clean_memory, clean_state, user_id):
    clean_memory({
        "name": "Alice",
        "current_streak": 5,
    })
    state = {
        "mode": "General",
        "clarification_pending": False,
        "clarification_count": 0,
        "data": {"goal": "complete python course"}
    }
    clean_state(state)

    result = execute_action("ask_clarification", user_id, "hi", state)
    
    assert result["type"] == "greeting_returning"
    assert "Welcome back Alice." in result["message"]
    assert "You were working on complete python course." in result["message"]
    assert "Current streak: 5 days." in result["message"]
    assert state["clarification_pending"] is False
    assert state["clarification_count"] == 0


@patch("services.trajectory.load_trajectory")
def test_returning_user_greeting_consistency(mock_load_trajectory, clean_memory, clean_state, user_id):
    mock_load_trajectory.return_value = {"consistency_score": 0.85}
    clean_memory({
        "name": "Bob",
        "current_streak": 0,
    })
    state = {
        "mode": "General",
        "clarification_pending": False,
        "clarification_count": 0,
    }
    clean_state(state)

    result = execute_action("ask_clarification", user_id, "hey", state)

    assert result["type"] == "greeting_returning"
    assert "Welcome back Bob." in result["message"]
    assert "Consistency: 85/100." in result["message"]
    assert state["clarification_pending"] is False
    assert state["clarification_count"] == 0


# ---------------------------------------------------------------------------
# FIX 4: News Classification Quality
# ---------------------------------------------------------------------------

def test_horoscope_not_ai():
    article = {
        "title": "Daily Horoscope: Will AI find you love today?",
        "description": "Read your astrology update to see how tech and zodiac intersect."
    }
    category = classify_news(article)
    priority = assign_priority(article)
    assert category == "General"
    assert priority == "LOW"


def test_ai_article_still_ai():
    article = {
        "title": "AI Breakthrough in NLP",
        "description": "Researchers launch a new LLM with amazing capabilities."
    }
    category = classify_news(article)
    priority = assign_priority(article)
    assert category == "AI"
    # Contains "launch", so priority is MEDIUM
    assert priority == "MEDIUM"


# ---------------------------------------------------------------------------
# FIX 5: Clarification State Machine
# ---------------------------------------------------------------------------

def test_clarification_pending(clean_memory, clean_state, user_id):
    clean_memory({})
    state = {
        "mode": "General",
        "clarification_pending": False,
        "clarification_count": 0,
    }
    clean_state(state)

    result = execute_action("ask_clarification", user_id, "some vague message", state)
    
    assert result["type"] == "clarification"
    assert result["question"] == "Tell me what you're trying to achieve."
    assert state["clarification_pending"] is True
    assert state["clarification_count"] == 1


def test_second_vague_response(clean_memory, clean_state, user_id):
    clean_memory({})
    state = {
        "mode": "General",
        "clarification_pending": True,
        "clarification_count": 1,
    }
    clean_state(state)

    result = execute_action("ask_clarification", user_id, "another vague response", state)

    assert result["type"] == "clarification"
    assert "I can help you study" in result["question"]
    assert state["clarification_pending"] is True
    assert state["clarification_count"] == 2


def test_clarification_resolved(clean_memory, clean_state, user_id):
    clean_memory({})
    state = {
        "mode": "General",
        "clarification_pending": True,
        "clarification_count": 2,
    }
    clean_state(state)

    # User provides a clear response matching STUDY intent, mapping to generate_plan action
    execute_action("generate_plan", user_id, "study computer science", state)

    assert state["clarification_pending"] is False
    assert state["clarification_count"] == 0


def test_clarification_loop_breakout(clean_memory, clean_state, user_id):
    clean_memory({})
    state = {
        "mode": "General",
        "clarification_pending": True,
        "clarification_count": 2,
    }
    clean_state(state)

    result = execute_action("ask_clarification", user_id, "vague three", state)

    assert result["type"] == "clarification"
    assert "Let's try creating a plan" in result["question"]
    assert state["clarification_pending"] is False
    assert state["clarification_count"] == 0
