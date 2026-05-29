"""JSON-backed user memory service for BOWA."""

import json
import threading
from pathlib import Path
from typing import Any


MEMORY_FILE = Path("memory.json")
_memory_lock = threading.Lock()
_memory_store_cache = None


def read_memory_store() -> dict[str, dict[str, Any]]:
    """Read the full memory store from disk."""
    global _memory_store_cache
    if _memory_store_cache is not None:
        return _memory_store_cache

    with _memory_lock:
        if _memory_store_cache is not None:
            return _memory_store_cache

        if not MEMORY_FILE.exists():
            _memory_store_cache = {}
            return _memory_store_cache

        try:
            with MEMORY_FILE.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except (json.JSONDecodeError, OSError):
            _memory_store_cache = {}
            return _memory_store_cache

        if not isinstance(data, dict):
            _memory_store_cache = {}
            return _memory_store_cache

        _memory_store_cache = data
        return _memory_store_cache


def write_memory_store(memory_store: dict[str, dict[str, Any]]) -> None:
    """Write the full memory store to disk."""
    global _memory_store_cache
    with _memory_lock:
        _memory_store_cache = memory_store
        with MEMORY_FILE.open("w", encoding="utf-8") as file:
            json.dump(memory_store, file, indent=2)


def load_user_memory(user_id: str | None) -> dict[str, Any]:
    """Load memory for a user ID."""
    if not user_id:
        return {}

    memory_store = read_memory_store()
    user_memory = memory_store.get(user_id, {})

    if not isinstance(user_memory, dict):
        return {}

    import copy
    return copy.deepcopy(user_memory)


def save_user_memory(user_id: str | None, data: dict[str, Any]) -> None:
    """Save memory for a user ID."""
    if not user_id:
        return

    memory_store = read_memory_store()
    import copy
    memory_store[user_id] = copy.deepcopy(data)
    write_memory_store(memory_store)


def should_store_value(value: Any) -> bool:
    """Return whether a value is useful enough to store."""
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    if isinstance(value, list) and not value:
        return False
    return True


def merge_memory_data(
    previous_data: dict[str, Any],
    new_data: dict[str, Any]
) -> dict[str, Any]:
    """Merge existing memory with new request data."""
    merged_data = previous_data.copy()

    for key, value in new_data.items():
        if key == "user_id":
            continue
        if should_store_value(value):
            merged_data[key] = value

    return merged_data


def update_user_memory(user_id: str | None, new_data: dict[str, Any]) -> dict[str, Any]:
    """Merge and persist memory for a user ID."""
    if not user_id:
        return {
            key: value
            for key, value in new_data.items()
            if key != "user_id" and should_store_value(value)
        }

    previous_data = load_user_memory(user_id)
    merged_data = merge_memory_data(previous_data, new_data)
    save_user_memory(user_id, merged_data)
    return merged_data


def calculate_habit_score(user_id: str) -> float:
    """Calculate a weighted habit score for the user."""
    memory = load_user_memory(user_id) or {}
    streak = memory.get("current_streak", 0)
    success_rate = memory.get("success_rate", 0)
    consistency = memory.get("consistency_score", 0.5)

    # Weighted score: 40% streak, 40% success rate, 20% consistency
    score = (streak * 0.4) + (success_rate * 0.4) + (consistency * 20)
    return min(100, score)
