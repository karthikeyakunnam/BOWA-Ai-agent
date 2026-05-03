"""JSON-backed user memory service for BOWA."""

import json
from pathlib import Path
from typing import Any


MEMORY_FILE = Path("memory.json")


def read_memory_store() -> dict[str, dict[str, Any]]:
    """Read the full memory store from disk."""
    if not MEMORY_FILE.exists():
        return {}

    try:
        with MEMORY_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, OSError):
        return {}

    if not isinstance(data, dict):
        return {}

    return data


def write_memory_store(memory_store: dict[str, dict[str, Any]]) -> None:
    """Write the full memory store to disk."""
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

    return user_memory


def save_user_memory(user_id: str | None, data: dict[str, Any]) -> None:
    """Save memory for a user ID."""
    if not user_id:
        return

    memory_store = read_memory_store()
    memory_store[user_id] = data
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
