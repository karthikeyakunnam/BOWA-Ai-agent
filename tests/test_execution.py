"""Tests for execution system — session lifecycle, duplicate prevention, completion."""

import pytest
from datetime import datetime, timedelta, timezone

from services.execution import (
    create_one_session_task,
    get_execution_session,
    start_execution_session,
    end_execution_session,
    check_expired_sessions,
    save_execution_session,
    get_session_status,
    _classify_news_task_outcome,
)


# ---------------------------------------------------------------------------
# Single active session enforcement
# ---------------------------------------------------------------------------
class TestOneActiveSession:

    def test_create_first_session(self, user_id):
        session = create_one_session_task(user_id, "study SQL", 25)
        assert session["active"] is True
        assert session["task"] == "study SQL"
        assert session["status"] == "running"

    def test_duplicate_blocked_when_running(self, user_id):
        first = create_one_session_task(user_id, "study SQL", 25)
        second = create_one_session_task(user_id, "study Python", 30)
        # second call returns the FIRST session, not a new one
        assert second["task"] == "study SQL"
        assert second == first  # matching contents returned

    def test_new_session_after_end(self, user_id, clean_memory):
        clean_memory({})
        create_one_session_task(user_id, "task A", 25)
        end_execution_session(user_id, True)
        new = create_one_session_task(user_id, "task B", 25)
        assert new["task"] == "task B"
        assert new["status"] == "running"

    def test_start_execution_session_is_alias(self, user_id):
        session = start_execution_session(user_id, "alias task", 15)
        assert session["active"] is True
        assert session["task"] == "alias task"


# ---------------------------------------------------------------------------
# Duplicate prevention
# ---------------------------------------------------------------------------
class TestDuplicatePrevention:

    def test_duplicate_returns_existing(self, user_id):
        create_one_session_task(user_id, "task X", 25)
        dup = create_one_session_task(user_id, "task Y", 30)
        assert dup["task"] == "task X"

    def test_expired_session_allows_new(self, user_id, clean_memory):
        clean_memory({})
        # Create a session that started 60 minutes ago (expired for 25-min duration)
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

        # get_execution_session should mark it expired
        loaded = get_execution_session(user_id)
        assert loaded["status"] == "expired"

        # But create_one_session_task still checks active + running
        # expired session is still active=True but status=expired, so it should allow new
        new = create_one_session_task(user_id, "new task", 25)
        assert new["task"] == "new task"


# ---------------------------------------------------------------------------
# Session expiry detection
# ---------------------------------------------------------------------------
class TestExpiredSessions:

    def test_running_session_not_expired(self, user_id):
        create_one_session_task(user_id, "active task", 25)
        expired = check_expired_sessions()
        assert len(expired) == 0

    def test_old_session_detected_expired(self, user_id):
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
        assert expired[0][0] == user_id


# ---------------------------------------------------------------------------
# Session completion
# ---------------------------------------------------------------------------
class TestSessionCompletion:

    def test_end_completed(self, user_id, clean_memory):
        clean_memory({})
        create_one_session_task(user_id, "done task", 25)
        end_execution_session(user_id, True)
        session = get_execution_session(user_id)
        assert session["status"] == "completed"
        assert session["active"] is False

    def test_end_failed(self, user_id, clean_memory):
        clean_memory({})
        create_one_session_task(user_id, "fail task", 25)
        end_execution_session(user_id, False)
        session = get_execution_session(user_id)
        assert session["status"] == "failed"
        assert session["active"] is False

    def test_end_nonexistent_session_no_crash(self, user_id):
        # Should not raise
        end_execution_session(user_id, True)


# ---------------------------------------------------------------------------
# Session status for UI
# ---------------------------------------------------------------------------
class TestSessionStatus:

    def test_no_session_status(self, user_id, clean_memory):
        clean_memory({})
        status = get_session_status(user_id)
        assert status["active"] is False

    def test_active_session_status(self, user_id, clean_memory):
        clean_memory({})
        create_one_session_task(user_id, "current task", 25)
        status = get_session_status(user_id)
        assert status["active"] is True
        assert status["task"] == "current task"
        assert status["remaining_seconds"] > 0


# ---------------------------------------------------------------------------
# News task outcome classification
# ---------------------------------------------------------------------------
class TestNewsTaskOutcome:

    def test_user_confirmed_completed(self):
        session = {"source_type": "news", "duration": 25,
                   "start_time": datetime.now(timezone.utc).isoformat()}
        assert _classify_news_task_outcome(session, user_confirmed=True) == "completed"

    def test_user_confirmed_abandoned(self):
        session = {"source_type": "news", "duration": 25,
                   "start_time": datetime.now(timezone.utc).isoformat()}
        assert _classify_news_task_outcome(session, user_confirmed=False) == "abandoned"

    def test_non_news_always_completed(self):
        session = {"source_type": "general", "duration": 25}
        assert _classify_news_task_outcome(session) == "completed"

    def test_missing_start_time_abandoned(self):
        session = {"source_type": "news", "duration": 25}
        assert _classify_news_task_outcome(session) == "abandoned"
