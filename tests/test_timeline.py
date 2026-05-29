"""Tests for BOWA event timeline system and timeline integrations."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from main import app
from event_timeline import append_event, get_user_timeline, TIMELINE_FILE
from services.conversation import handle_user_message
from services.execution import (
    create_one_session_task,
    end_execution_session,
    check_expired_sessions,
    save_execution_session,
)
from services.news_feedback import capture_user_reaction
from services.goal_engine import set_user_goal
from services.proactive import save_proactive_message
from services.state import update_user_state, build_initial_state


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def isolate_timeline(tmp_path, monkeypatch):
    """Isolate timeline file in temp path."""
    timeline_file = tmp_path / "event_timeline.json"
    monkeypatch.setattr("event_timeline.TIMELINE_FILE", timeline_file)
    yield timeline_file


def test_append_and_get_events(user_id):
    """Test basic appending and reading timeline events."""
    append_event(user_id, "test_event_1", {"key": "val1"})
    append_event(user_id, "test_event_2", {"key": "val2"})

    timeline = get_user_timeline(user_id)
    assert len(timeline) == 2
    assert timeline[0]["event_type"] == "test_event_1"
    assert timeline[0]["metadata"] == {"key": "val1"}
    assert timeline[1]["event_type"] == "test_event_2"
    assert timeline[1]["metadata"] == {"key": "val2"}


def test_timeline_caps_at_100(user_id):
    """Timeline store should drop old events to cap at 100."""
    for i in range(120):
        append_event(user_id, f"event_{i}", {"index": i})

    timeline = get_user_timeline(user_id)
    assert len(timeline) == 100
    assert timeline[0]["event_type"] == "event_20"
    assert timeline[-1]["event_type"] == "event_119"


def test_message_received_event(user_id, clean_memory):
    """handle_user_message should record message_received event."""
    clean_memory({})
    handle_user_message(user_id, "hello BOWA, please plan my day")

    timeline = get_user_timeline(user_id)
    assert len(timeline) >= 1
    events = [e for e in timeline if e["event_type"] == "message_received"]
    assert len(events) == 1
    assert "hello BOWA" in events[0]["metadata"]["message"]


def test_news_clicked_event(user_id, clean_memory):
    """capture_user_reaction should record news_clicked when action is clicked."""
    clean_memory({})
    capture_user_reaction(
        user_id=user_id,
        news_title="OpenAI releases GPT-5",
        category="AI",
        action_suggested="act",
        user_action="clicked",
    )

    timeline = get_user_timeline(user_id)
    events = [e for e in timeline if e["event_type"] == "news_clicked"]
    assert len(events) == 1
    assert events[0]["metadata"]["title"] == "OpenAI releases GPT-5"


def test_execution_started_and_completed_events(user_id, clean_memory):
    """Execution sessions should write execution_started and execution_completed events."""
    clean_memory({})
    
    # 1. Start Session
    create_one_session_task(user_id, "learn Python", 25)
    timeline = get_user_timeline(user_id)
    assert any(e["event_type"] == "execution_started" for e in timeline)

    # 2. End Session
    end_execution_session(user_id, True)
    timeline = get_user_timeline(user_id)
    assert any(e["event_type"] == "execution_completed" for e in timeline)
    completed_event = [e for e in timeline if e["event_type"] == "execution_completed"][0]
    assert completed_event["metadata"]["completed"] is True


def test_expired_execution_records_event(user_id, clean_memory):
    """Expired sessions should log an execution_completed event."""
    clean_memory({})
    past = datetime.now(timezone.utc) - timedelta(minutes=60)
    session = {
        "active": True,
        "task": "old task",
        "duration": 25,
        "start_time": past.isoformat(),
        "status": "running",
        "source_type": "general",
        "news_id": "",
        "category": "",
    }
    save_execution_session(user_id, session)
    
    expired = check_expired_sessions()
    assert len(expired) == 1

    timeline = get_user_timeline(user_id)
    expired_event = [e for e in timeline if e["event_type"] == "execution_completed"][0]
    assert expired_event["metadata"]["status"] == "expired"
    assert expired_event["metadata"]["completed"] is False


def test_goal_updated_interceptor(user_id, clean_memory):
    """set_user_goal should automatically append goal_updated via interceptor."""
    clean_memory({})
    set_user_goal(user_id, "Learn Quantum Computing")
    
    timeline = get_user_timeline(user_id)
    events = [e for e in timeline if e["event_type"] == "goal_updated"]
    assert len(events) == 1
    assert events[0]["metadata"]["goal"] == "Learn Quantum Computing"


def test_notification_sent_interceptor(user_id, clean_memory, monkeypatch, tmp_path):
    """save_proactive_message should log notification_sent event."""
    clean_memory({})
    notifs_file = tmp_path / "notifications.json"
    monkeypatch.setattr("services.proactive.NOTIFICATIONS_FILE", notifs_file)

    save_proactive_message(user_id, "Don't fall behind!", "cooldown check", cooldown_hours=0)

    timeline = get_user_timeline(user_id)
    events = [e for e in timeline if e["event_type"] == "notification_sent"]
    assert len(events) == 1
    assert "Don't fall behind!" in events[0]["metadata"]["message"]


def test_plan_created_and_completed_interceptor(user_id, clean_state):
    """State updates containing new plans or completed plans should trigger timeline events."""
    clean_state({})
    
    # 1. Create a plan
    state = build_initial_state("Tracker")
    state["active_plan"] = {
        "goal": "Build a compiler",
        "steps": [{"step": 1, "action": "lexing", "done": False}],
        "completed": False
    }
    update_user_state(user_id, state)

    timeline = get_user_timeline(user_id)
    assert any(e["event_type"] == "plan_created" for e in timeline)
    created_event = [e for e in timeline if e["event_type"] == "plan_created"][0]
    assert created_event["metadata"]["goal"] == "Build a compiler"

    # 2. Complete the plan
    state["active_plan"]["completed"] = True
    update_user_state(user_id, state)

    timeline = get_user_timeline(user_id)
    assert any(e["event_type"] == "plan_completed" for e in timeline)
    completed_event = [e for e in timeline if e["event_type"] == "plan_completed"][0]
    assert completed_event["metadata"]["goal"] == "Build a compiler"


def test_timeline_endpoint(client, user_id):
    """GET /timeline/{user_id} should return latest timeline events."""
    append_event(user_id, "endpoint_check", {"success": True})
    
    response = client.get(f"/timeline/{user_id}")
    assert response.status_code == 200
    
    data = response.json()
    assert len(data) == 1
    assert data[0]["event_type"] == "endpoint_check"
    assert data[0]["metadata"] == {"success": True}
