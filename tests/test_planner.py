"""Tests for planner system — plan generation, progression, duplicate prevention."""

import pytest

from services.planner_engine import generate_plan, _is_large_goal, _normalize_plan_steps
from services.actions import _advance_active_plan


# ---------------------------------------------------------------------------
# _is_large_goal — controls when plans are generated
# ---------------------------------------------------------------------------
class TestIsLargeGoal:

    def test_study_intent_is_large(self):
        assert _is_large_goal("study", "tell me") is True

    def test_jobs_intent_is_large(self):
        assert _is_large_goal("jobs", "anything") is True

    def test_tracker_intent_is_large(self):
        assert _is_large_goal("tracker", "ok") is True

    def test_keyword_match(self):
        assert _is_large_goal("general", "I want to learn Python") is True
        assert _is_large_goal("general", "become a data analyst") is True

    def test_short_general_message_not_large(self):
        """After FIX-10, messages >5 words alone should NOT trigger plan."""
        assert _is_large_goal("general", "show me the latest AI news today") is False

    def test_vague_message_not_large(self):
        assert _is_large_goal("general", "hmm ok") is False

    def test_greeting_not_large(self):
        assert _is_large_goal("general", "hello") is False


# ---------------------------------------------------------------------------
# generate_plan — skip conditions and plan structure
# ---------------------------------------------------------------------------
class TestGeneratePlan:

    def test_generates_plan_for_study(self):
        state = {}
        plan = generate_plan(state, "study", "learn SQL")
        assert plan is not None
        assert plan["current_step"] == 1
        assert plan["completed"] is False
        assert len(plan["steps"]) > 0

    def test_skips_when_executing(self):
        state = {"trajectory": {"current_stage": "executing"}}
        plan = generate_plan(state, "study", "learn SQL")
        assert plan is None

    def test_skips_when_confused(self):
        state = {"mood": "confused"}
        plan = generate_plan(state, "study", "learn SQL")
        assert plan is None

    def test_skips_when_active_plan_exists(self):
        state = {
            "active_plan": {
                "goal": "existing",
                "steps": [{"action": "step 1"}],
                "current_step": 1,
                "total_steps": 1,
                "completed": False,
            }
        }
        plan = generate_plan(state, "study", "learn SQL")
        assert plan is None

    def test_allows_plan_when_previous_completed(self):
        state = {
            "active_plan": {
                "goal": "old",
                "steps": [],
                "current_step": 1,
                "total_steps": 0,
                "completed": True,
            }
        }
        plan = generate_plan(state, "study", "learn SQL")
        assert plan is not None

    def test_no_plan_for_general_vague(self):
        plan = generate_plan({}, "general", "ok")
        assert plan is None


# ---------------------------------------------------------------------------
# _normalize_plan_steps — structure validation
# ---------------------------------------------------------------------------
class TestNormalizePlanSteps:

    def test_normalizes_dicts(self):
        raw = [{"action": "step A"}, {"action": "step B"}]
        result = _normalize_plan_steps(raw)
        assert len(result) == 2
        assert result[0]["step"] == 1
        assert result[0]["action"] == "step A"
        assert result[0]["done"] is False
        assert result[1]["step"] == 2

    def test_normalizes_non_dicts(self):
        raw = ["do this", "then that"]
        result = _normalize_plan_steps(raw)
        assert result[0]["action"] == "do this"
        assert result[1]["action"] == "then that"

    def test_empty_input(self):
        result = _normalize_plan_steps([])
        assert result == []


# ---------------------------------------------------------------------------
# _advance_active_plan — progression and completion
# ---------------------------------------------------------------------------
class TestAdvanceActivePlan:

    def test_advance_block_plan(self):
        plan = {
            "blocks": [
                {"block": 1, "task": "first", "done": False},
                {"block": 2, "task": "second", "done": False},
            ]
        }
        result = _advance_active_plan(plan)
        assert plan["blocks"][0]["done"] is True
        assert "second" in result

    def test_complete_block_plan(self):
        plan = {
            "blocks": [
                {"block": 1, "task": "only one", "done": False},
            ]
        }
        result = _advance_active_plan(plan)
        assert plan["completed"] is True

    def test_advance_step_plan(self):
        plan = {
            "steps": [
                {"step": 1, "action": "first", "done": False},
                {"step": 2, "action": "second", "done": False},
            ],
            "current_step": 1,
        }
        result = _advance_active_plan(plan)
        assert plan["steps"][0]["done"] is True
        assert plan["current_step"] == 2
        assert "second" in result

    def test_complete_step_plan(self):
        plan = {
            "steps": [
                {"step": 1, "action": "only one", "done": False},
            ],
            "current_step": 1,
        }
        result = _advance_active_plan(plan)
        assert plan["completed"] is True

    def test_no_duplicate_steps_on_advance(self):
        """Advancing should not duplicate step entries."""
        plan = {
            "steps": [
                {"step": 1, "action": "a"},
                {"step": 2, "action": "b"},
                {"step": 3, "action": "c"},
            ],
            "current_step": 1,
        }
        _advance_active_plan(plan)
        _advance_active_plan(plan)
        assert len(plan["steps"]) == 3  # no duplicates added
        assert plan["current_step"] == 3

    def test_none_plan_returns_none(self):
        assert _advance_active_plan(None) is None

    def test_empty_plan_returns_fallback(self):
        result = _advance_active_plan({})
        assert isinstance(result, str)
