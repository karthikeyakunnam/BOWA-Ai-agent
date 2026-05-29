"""Tests for memory system — save, load, merge, thread safety."""

import pytest
import threading

from services.memory import (
    load_user_memory,
    save_user_memory,
    read_memory_store,
    write_memory_store,
    merge_memory_data,
    update_user_memory,
    should_store_value,
    calculate_habit_score,
)


# ---------------------------------------------------------------------------
# Save and Load
# ---------------------------------------------------------------------------
class TestSaveLoad:

    def test_save_and_load(self, user_id):
        save_user_memory(user_id, {"goal": "learn SQL", "streak": 3})
        loaded = load_user_memory(user_id)
        assert loaded["goal"] == "learn SQL"
        assert loaded["streak"] == 3

    def test_load_nonexistent_user(self):
        loaded = load_user_memory("nonexistent_user_xyz")
        assert loaded == {}

    def test_load_none_user_id(self):
        loaded = load_user_memory(None)
        assert loaded == {}

    def test_save_none_user_id_no_crash(self):
        # Should not raise
        save_user_memory(None, {"data": "value"})

    def test_overwrite_existing(self, user_id):
        save_user_memory(user_id, {"version": 1})
        save_user_memory(user_id, {"version": 2})
        loaded = load_user_memory(user_id)
        assert loaded["version"] == 2

    def test_save_preserves_other_users(self, user_id):
        save_user_memory("user_a", {"name": "A"})
        save_user_memory("user_b", {"name": "B"})
        a = load_user_memory("user_a")
        b = load_user_memory("user_b")
        assert a["name"] == "A"
        assert b["name"] == "B"

    def test_full_store_read_write(self):
        data = {"u1": {"x": 1}, "u2": {"y": 2}}
        write_memory_store(data)
        loaded = read_memory_store()
        assert loaded["u1"]["x"] == 1
        assert loaded["u2"]["y"] == 2


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------
class TestMerge:

    def test_merge_adds_new_keys(self):
        previous = {"goal": "old"}
        new = {"streak": 5}
        merged = merge_memory_data(previous, new)
        assert merged["goal"] == "old"
        assert merged["streak"] == 5

    def test_merge_overwrites_existing_keys(self):
        previous = {"goal": "old"}
        new = {"goal": "new"}
        merged = merge_memory_data(previous, new)
        assert merged["goal"] == "new"

    def test_merge_skips_user_id(self):
        previous = {}
        new = {"user_id": "u1", "goal": "test"}
        merged = merge_memory_data(previous, new)
        assert "user_id" not in merged
        assert merged["goal"] == "test"

    def test_merge_skips_none_values(self):
        previous = {"goal": "keep"}
        new = {"goal": None}
        merged = merge_memory_data(previous, new)
        assert merged["goal"] == "keep"

    def test_merge_skips_empty_string(self):
        previous = {"goal": "keep"}
        new = {"goal": "  "}
        merged = merge_memory_data(previous, new)
        assert merged["goal"] == "keep"

    def test_merge_skips_empty_list(self):
        previous = {"skills": ["python"]}
        new = {"skills": []}
        merged = merge_memory_data(previous, new)
        assert merged["skills"] == ["python"]

    def test_update_user_memory_merges(self, user_id):
        save_user_memory(user_id, {"goal": "SQL", "streak": 1})
        result = update_user_memory(user_id, {"streak": 5, "mood": "focused"})
        assert result["goal"] == "SQL"
        assert result["streak"] == 5
        assert result["mood"] == "focused"


# ---------------------------------------------------------------------------
# should_store_value
# ---------------------------------------------------------------------------
class TestShouldStoreValue:

    def test_none_not_stored(self):
        assert should_store_value(None) is False

    def test_empty_string_not_stored(self):
        assert should_store_value("") is False
        assert should_store_value("  ") is False

    def test_empty_list_not_stored(self):
        assert should_store_value([]) is False

    def test_valid_string_stored(self):
        assert should_store_value("hello") is True

    def test_zero_stored(self):
        assert should_store_value(0) is True

    def test_false_stored(self):
        assert should_store_value(False) is True

    def test_nonempty_list_stored(self):
        assert should_store_value(["a"]) is True


# ---------------------------------------------------------------------------
# Thread safety (basic contention test)
# ---------------------------------------------------------------------------
class TestThreadSafety:

    def test_concurrent_writes_no_corruption(self, user_id):
        """Multiple threads writing to memory should not corrupt the file."""
        errors = []
        lock = threading.Lock()

        def writer(thread_id):
            try:
                for i in range(10):
                    with lock:
                        save_user_memory(
                            f"{user_id}_{thread_id}",
                            {"thread": thread_id, "iter": i},
                        )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(t,)) for t in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

        # Verify all users still have valid data
        store = read_memory_store()
        for t in range(5):
            key = f"{user_id}_{t}"
            assert key in store
            assert isinstance(store[key], dict)


# ---------------------------------------------------------------------------
# calculate_habit_score
# ---------------------------------------------------------------------------
class TestHabitScore:

    def test_default_score(self, user_id):
        save_user_memory(user_id, {})
        score = calculate_habit_score(user_id)
        # Default: streak=0 * 0.4 + success_rate=0 * 0.4 + consistency=0.5 * 20 = 10
        assert score == 10.0

    def test_high_score(self, user_id):
        save_user_memory(user_id, {
            "current_streak": 10,
            "success_rate": 80,
            "consistency_score": 0.9,
        })
        score = calculate_habit_score(user_id)
        # 10*0.4 + 80*0.4 + 0.9*20 = 4 + 32 + 18 = 54
        assert score == 54.0

    def test_score_capped_at_100(self, user_id):
        save_user_memory(user_id, {
            "current_streak": 200,
            "success_rate": 100,
            "consistency_score": 1.0,
        })
        score = calculate_habit_score(user_id)
        assert score == 100
