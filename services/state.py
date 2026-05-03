"""Persistent conversation state storage for BOWA.

JSON-backed state store that tracks where each user is in their
conversation flow. Survives server restarts.
"""

import json
from pathlib import Path
from typing import Any


STATE_FILE = Path("state.json")


def _read_store() -> dict[str, dict[str, Any]]:
    """Read the full state store from disk."""
    if not STATE_FILE.exists():
        return {}

    try:
        with STATE_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}

    if not isinstance(data, dict):
        return {}

    return data


def _write_store(store: dict[str, dict[str, Any]]) -> None:
    """Write the full state store to disk."""
    with STATE_FILE.open("w", encoding="utf-8") as f:
        json.dump(store, f, indent=2)


def get_user_state(user_id: str) -> dict[str, Any] | None:
    """Get conversation state for a user. Returns None if no state."""
    store = _read_store()
    state = store.get(user_id)

    if not isinstance(state, dict):
        return None

    return state


def update_user_state(user_id: str, state: dict[str, Any]) -> dict[str, Any]:
    """Update and persist conversation state for a user."""
    store = _read_store()
    store[user_id] = state
    _write_store(store)
    return state


def reset_state(user_id: str) -> None:
    """Clear conversation state for a user."""
    store = _read_store()
    if user_id in store:
        del store[user_id]
        _write_store(store)


def build_initial_state(mode: str) -> dict[str, Any]:
    """Create a fresh state structure for a given mode."""
    return {
        "mode": mode,
        "stage": "init",
        "data": {
            "topic": "",
            "goal": "",
            "skills": [],
            "role": "",
            "location": "",
            "hours": "",
            "task": "",
        },
    }
