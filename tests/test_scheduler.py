"""Tests for scheduler — notification cooldown, plan generation, session guards."""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from services.scheduler import (
    should_generate_daily_plan,
    merge_recent_notifications,
    SCHEDULER_INTERVAL_SECONDS,
)
from services.proactive import (
    save_proactive_message,
    get_user_notifications,
    generate_proactive_message,
    _calculate_adaptive_cooldown,
)
from services.memory import save_user_memory, load_user_memory


# ---------------------------------------------------------------------------
# Scheduler interval
# ---------------------------------------------------------------------------
class TestSchedulerConfig:

    def test_interval_is_reasonable(self):
        """After FIX-14, scheduler should run at 5-min intervals, not 30s."""
        assert SCHEDULER_INTERVAL_SECONDS >= 60


# ---------------------------------------------------------------------------
# Notification cooldown
# ---------------------------------------------------------------------------
class TestNotificationCooldown:

    def test_first_message_always_saved(self, user_id):
        save_proactive_message(user_id, "first msg", "test_reason")
        notifications = get_user_notifications(user_id)
        assert len(notifications) == 1
        assert notifications[0]["message"] == "first msg"

    def test_same_reason_blocked_within_cooldown(self, user_id):
        save_proactive_message(user_id, "msg 1", "same_reason", cooldown_hours=6)
        save_proactive_message(user_id, "msg 2", "same_reason", cooldown_hours=6)
        notifications = get_user_notifications(user_id)
        # Second message should be blocked by cooldown
        assert len(notifications) == 1

    def test_different_reason_allowed(self, user_id):
        save_proactive_message(user_id, "msg A", "reason_a")
        save_proactive_message(user_id, "msg B", "reason_b")
        notifications = get_user_notifications(user_id)
        assert len(notifications) == 2

    def test_daily_limit_enforced(self, user_id):
        """No more than 2 messages per day regardless of reason."""
        save_proactive_message(user_id, "msg 1", "reason_1", cooldown_hours=0)
        save_proactive_message(user_id, "msg 2", "reason_2", cooldown_hours=0)
        save_proactive_message(user_id, "msg 3", "reason_3", cooldown_hours=0)
        notifications = get_user_notifications(user_id)
        assert len(notifications) <= 2

    def test_notifications_capped_at_10(self, user_id):
        """Store should keep at most 10 notifications per user."""
        for i in range(15):
            save_proactive_message(user_id, f"msg {i}", f"reason_{i}", cooldown_hours=0)
        notifications = get_user_notifications(user_id)
        assert len(notifications) <= 10

    def test_corrupted_timestamp_no_crash(self, user_id):
        """After FIX-7, invalid timestamps should not crash the function."""
        from services.proactive import write_notifications_store
        # Write a notification with bad timestamp
        write_notifications_store({
            user_id: [{"timestamp": "INVALID", "message": "old", "reason": "x"}]
        })
        # Should not raise
        save_proactive_message(user_id, "new msg", "new_reason")
        notifications = get_user_notifications(user_id)
        assert len(notifications) >= 1

    def test_notification_cooldown_prevents_duplicates(self, user_id):
        save_proactive_message(user_id, "Unique Message A", "reason_a", cooldown_hours=6)
        save_proactive_message(user_id, "Unique Message B", "reason_a", cooldown_hours=6)
        notifications = get_user_notifications(user_id)
        assert len(notifications) == 1
        assert notifications[0]["message"] == "Unique Message A"

    def test_same_notification_not_saved_twice(self, user_id):
        save_proactive_message(user_id, "Repeated Message", "reason_x", cooldown_hours=0)
        save_proactive_message(user_id, "Repeated Message", "reason_y", cooldown_hours=0)
        notifications = get_user_notifications(user_id)
        assert len(notifications) == 1
        assert notifications[0]["message"] == "Repeated Message"


# ---------------------------------------------------------------------------
# Adaptive cooldown
# ---------------------------------------------------------------------------
class TestAdaptiveCooldown:

    def test_default_cooldown(self, user_id, clean_memory):
        clean_memory({})
        cooldown = _calculate_adaptive_cooldown(user_id, base_cooldown=6)
        assert cooldown == 6

    def test_recently_active_doubles_cooldown(self, user_id, clean_memory):
        recent = datetime.now(timezone.utc) - timedelta(hours=2)
        clean_memory({"last_active": recent.isoformat()})
        cooldown = _calculate_adaptive_cooldown(user_id, base_cooldown=6)
        assert cooldown == 12

    def test_inactive_24h_zero_cooldown(self, user_id, clean_memory):
        old = datetime.now(timezone.utc) - timedelta(hours=30)
        clean_memory({"last_active": old.isoformat()})
        cooldown = _calculate_adaptive_cooldown(user_id, base_cooldown=6)
        assert cooldown == 0


# ---------------------------------------------------------------------------
# Plan generation guard
# ---------------------------------------------------------------------------
class TestPlanGeneration:

    def test_should_generate_when_goal_exists_no_plan(self):
        assert should_generate_daily_plan("u1", {"goal": "learn SQL"}) is True

    def test_should_not_generate_without_goal(self):
        assert should_generate_daily_plan("u1", {}) is False

    def test_should_not_regenerate_same_day(self):
        today = datetime.now(timezone.utc).isoformat()
        user_data = {
            "goal": "learn SQL",
            "daily_plan": {"created_at": today},
        }
        assert should_generate_daily_plan("u1", user_data) is False

    def test_should_regenerate_next_day(self):
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        user_data = {
            "goal": "learn SQL",
            "daily_plan": {"created_at": yesterday},
        }
        assert should_generate_daily_plan("u1", user_data) is True

    def test_invalid_date_regenerates(self):
        user_data = {
            "goal": "learn SQL",
            "daily_plan": {"created_at": "NOT_A_DATE"},
        }
        assert should_generate_daily_plan("u1", user_data) is True


# ---------------------------------------------------------------------------
# merge_recent_notifications
# ---------------------------------------------------------------------------
class TestMergeNotifications:

    def test_new_first(self):
        old = [{"message": "old"}]
        new = [{"message": "new"}]
        merged = merge_recent_notifications(old, new)
        assert merged[0]["message"] == "new"

    def test_capped_at_10(self):
        old = [{"message": f"old_{i}"} for i in range(8)]
        new = [{"message": f"new_{i}"} for i in range(8)]
        merged = merge_recent_notifications(old, new)
        assert len(merged) == 10

    def test_empty_inputs(self):
        assert merge_recent_notifications([], []) == []


# ---------------------------------------------------------------------------
# Proactive message generation
# ---------------------------------------------------------------------------
class TestProactiveMessageGeneration:

    def test_inactive_24h_triggers(self):
        old = datetime.now(timezone.utc) - timedelta(hours=25)
        state = {"last_active": old.isoformat()}
        result = generate_proactive_message(state)
        assert result is not None
        msg, reason = result
        assert "consistency" in msg.lower() or "breaking" in msg.lower()

    def test_consistency_dropping_triggers(self):
        state = {"consistency_score": 0.3, "prev_consistency_score": 0.6}
        result = generate_proactive_message(state)
        assert result is not None
        _, reason = result
        assert reason == "consistency_dropping"

    def test_no_trigger_on_normal_state(self):
        now = datetime.now(timezone.utc).isoformat()
        state = {
            "last_active": now,
            "consistency_score": 0.5,
            "prev_consistency_score": 0.5,
            "stage": "planning",
            "progress": 1,
        }
        result = generate_proactive_message(state)
        assert result is None

    def test_high_consistency_triggers_increase(self):
        now = datetime.now(timezone.utc).isoformat()
        state = {
            "last_active": now,
            "consistency_score": 0.9,
            "prev_consistency_score": 0.85,
        }
        result = generate_proactive_message(state)
        assert result is not None
        _, reason = result
        assert reason == "consistent"
