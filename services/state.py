"""Persistent conversation state storage for BOWA.

JSON-backed state store that tracks where each user is in their
conversation flow. Survives server restarts.
"""

import json
from pathlib import Path
from typing import Any


import threading

STATE_FILE = Path("state.json")
_state_lock = threading.Lock()
_state_store_cache = None


def _read_store() -> dict[str, dict[str, Any]]:
    """Read the full state store from disk."""
    global _state_store_cache
    if _state_store_cache is not None:
        return _state_store_cache

    with _state_lock:
        if _state_store_cache is not None:
            return _state_store_cache

        if not STATE_FILE.exists():
            _state_store_cache = {}
            return _state_store_cache

        try:
            with STATE_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            _state_store_cache = {}
            return _state_store_cache

        if not isinstance(data, dict):
            _state_store_cache = {}
            return _state_store_cache

        _state_store_cache = data
        return _state_store_cache


def _write_store(store: dict[str, dict[str, Any]]) -> None:
    """Write the full state store to disk."""
    global _state_store_cache
    with _state_lock:
        _state_store_cache = store
        with STATE_FILE.open("w", encoding="utf-8") as f:
            json.dump(store, f, indent=2)


def get_user_state(user_id: str, mode: str | None = None) -> dict[str, Any] | None:
    """Get conversation state for a user and mode. Returns None if no state."""
    store = _read_store()
    user_entry = store.get(user_id)
    if not isinstance(user_entry, dict):
        return None

    # Migration for old-style state
    if "modes" not in user_entry:
        old_mode = user_entry.get("mode", "General")
        user_entry = {
            "active_mode": old_mode,
            "modes": {
                old_mode.lower(): user_entry
            }
        }
        store[user_id] = user_entry

    if not mode:
        mode = user_entry.get("active_mode", "General")

    state = user_entry.get("modes", {}).get(mode.lower())
    if not isinstance(state, dict):
        return None

    import copy
    return copy.deepcopy(state)


def update_user_state(user_id: str, state: dict[str, Any]) -> dict[str, Any]:
    """Update and persist conversation state for a user and mode."""
    store = _read_store()
    user_entry = store.get(user_id)

    # Initialize user_entry if not exists
    if not isinstance(user_entry, dict) or "modes" not in user_entry:
        user_entry = {
            "active_mode": "General",
            "modes": {}
        }

    import copy
    mode = state.get("mode", "General")
    user_entry["active_mode"] = mode
    user_entry["modes"][mode.lower()] = copy.deepcopy(state)

    store[user_id] = user_entry
    _write_store(store)
    return state


def reset_state(user_id: str, mode: str | None = None) -> None:
    """Clear conversation state for a user (optionally for a specific mode)."""
    store = _read_store()
    user_entry = store.get(user_id)
    if not isinstance(user_entry, dict):
        return

    if "modes" not in user_entry:
        old_mode = user_entry.get("mode", "General")
        user_entry = {
            "active_mode": old_mode,
            "modes": {
                old_mode.lower(): user_entry
            }
        }

    if mode:
        if mode.lower() in user_entry.get("modes", {}):
            del user_entry["modes"][mode.lower()]
    else:
        active_mode = user_entry.get("active_mode", "General")
        if active_mode.lower() in user_entry.get("modes", {}):
            del user_entry["modes"][active_mode.lower()]

    store[user_id] = user_entry
    _write_store(store)


def set_active_mode(user_id: str, mode: str) -> None:
    """Set the active mode for the user without modifying other fields."""
    store = _read_store()
    user_entry = store.get(user_id)
    if not isinstance(user_entry, dict) or "modes" not in user_entry:
        user_entry = {
            "active_mode": mode,
            "modes": {}
        }
    else:
        user_entry["active_mode"] = mode

    store[user_id] = user_entry
    _write_store(store)


def build_initial_state(mode: str) -> dict[str, Any]:
    """Create a fresh state structure for a given mode."""
    return {
        "mode": mode,
        "stage": "init",
        "last_reply": "",
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
