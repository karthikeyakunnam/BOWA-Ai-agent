"""Tests for news system — act, watch, ignore actions and deduplication."""

import pytest
from unittest.mock import patch

from services.conversation import _handle_news_action
from services.memory import load_user_memory, save_user_memory


# ---------------------------------------------------------------------------
# News action: act
# ---------------------------------------------------------------------------
class TestNewsAct:

    @patch("services.conversation.capture_user_reaction")
    @patch("services.conversation._update_news_escalation_count")
    def test_act_creates_session(self, mock_esc, mock_reaction, user_id, clean_memory):
        clean_memory({})
        result = _handle_news_action(
            user_id, "act", "AI company launches new tool", "learn AI", "high"
        )
        assert result["action"] == "act"
        assert result["status"] == "created"
        assert "task" in result
        assert result["duration"] >= 15

    @patch("services.conversation.capture_user_reaction")
    @patch("services.conversation._update_news_escalation_count")
    def test_act_prevents_duplicate(self, mock_esc, mock_reaction, user_id, clean_memory):
        clean_memory({})
        # First act creates session
        _handle_news_action(user_id, "act", "first news", "goal", "low")
        # Second act should detect running session
        result = _handle_news_action(user_id, "act", "second news", "goal", "low")
        assert result["status"] == "duplicate"

    @patch("services.conversation.capture_user_reaction")
    @patch("services.conversation._update_news_escalation_count")
    def test_act_categorizes_ai(self, mock_esc, mock_reaction, user_id, clean_memory):
        clean_memory({})
        result = _handle_news_action(
            user_id, "act", "AI breakthrough in machine learning", "learn AI", "high"
        )
        assert result["status"] == "created"
        # Category detection is internal, verified through capture_user_reaction call
        mock_reaction.assert_called_once()
        call_kwargs = mock_reaction.call_args
        assert call_kwargs[1]["category"] == "AI" or call_kwargs[0][2] == "AI"


# ---------------------------------------------------------------------------
# News action: watch
# ---------------------------------------------------------------------------
class TestNewsWatch:

    @patch("services.conversation.capture_user_reaction")
    def test_watch_adds_to_list(self, mock_reaction, user_id, clean_memory):
        clean_memory({})
        result = _handle_news_action(
            user_id, "watch", "stock market drops", "finance career", "medium"
        )
        assert result["action"] == "watch"
        assert result["status"] == "tracked"

        memory = load_user_memory(user_id)
        assert len(memory["watch_list"]) == 1
        assert memory["watch_list"][0]["category"] == "Finance"

    @patch("services.conversation.capture_user_reaction")
    def test_watch_deduplicates(self, mock_reaction, user_id, clean_memory):
        clean_memory({})
        _handle_news_action(user_id, "watch", "same news item", "goal", "low")
        result = _handle_news_action(user_id, "watch", "same news item", "goal", "low")
        assert result["status"] == "duplicate"

        memory = load_user_memory(user_id)
        assert len(memory["watch_list"]) == 1

    @patch("services.conversation.capture_user_reaction")
    def test_watch_list_capped_at_20(self, mock_reaction, user_id, clean_memory):
        clean_memory({})
        for i in range(25):
            _handle_news_action(
                user_id, "watch", f"unique news item {i}", "goal", "low"
            )

        memory = load_user_memory(user_id)
        assert len(memory["watch_list"]) <= 20


# ---------------------------------------------------------------------------
# News action: ignore
# ---------------------------------------------------------------------------
class TestNewsIgnore:

    @patch("services.conversation.capture_user_reaction")
    def test_ignore_logs_and_skips(self, mock_reaction, user_id, clean_memory):
        clean_memory({})
        result = _handle_news_action(
            user_id, "ignore", "irrelevant news", "my goal", "low"
        )
        assert result["action"] == "ignore"
        assert result["status"] == "skipped"

        memory = load_user_memory(user_id)
        assert len(memory["ignored_news"]) == 1

    @patch("services.conversation.capture_user_reaction")
    def test_ignore_tracks_reason(self, mock_reaction, user_id, clean_memory):
        clean_memory({})
        _handle_news_action(user_id, "ignore", "not for me", "goal", "low")
        memory = load_user_memory(user_id)
        assert memory["ignored_news"][0]["reason"] == "not_relevant"


# ---------------------------------------------------------------------------
# News action: unknown
# ---------------------------------------------------------------------------
class TestNewsUnknownAction:

    def test_unknown_action_returns_error(self, user_id, clean_memory):
        clean_memory({})
        result = _handle_news_action(user_id, "bogus", "content", "goal", "low")
        assert result["action"] == "unknown"
        assert result["status"] == "error"


# ---------------------------------------------------------------------------
# Category detection
# ---------------------------------------------------------------------------
class TestNewsCategoryDetection:

    @patch("services.conversation.capture_user_reaction")
    def test_ai_category(self, mock_reaction, user_id, clean_memory):
        clean_memory({})
        _handle_news_action(user_id, "ignore", "AI tech software launch", "g", "low")
        memory = load_user_memory(user_id)
        assert memory["ignored_news"][0]["category"] == "AI"

    @patch("services.conversation.capture_user_reaction")
    def test_jobs_category(self, mock_reaction, user_id, clean_memory):
        clean_memory({})
        _handle_news_action(user_id, "ignore", "hiring freeze at company", "g", "low")
        memory = load_user_memory(user_id)
        assert memory["ignored_news"][0]["category"] == "Jobs"

    @patch("services.conversation.capture_user_reaction")
    def test_finance_category(self, mock_reaction, user_id, clean_memory):
        clean_memory({})
        _handle_news_action(user_id, "ignore", "stock market economy crash", "g", "low")
        memory = load_user_memory(user_id)
        assert memory["ignored_news"][0]["category"] == "Finance"

    @patch("services.conversation.capture_user_reaction")
    def test_general_category_fallback(self, mock_reaction, user_id, clean_memory):
        clean_memory({})
        _handle_news_action(user_id, "ignore", "sports update today", "g", "low")
        memory = load_user_memory(user_id)
        assert memory["ignored_news"][0]["category"] == "General"
