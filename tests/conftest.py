"""Shared test fixtures and helpers for BOWA test suite."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def isolate_json_files(tmp_path, monkeypatch):
    """Redirect all JSON-backed stores to temp dir so tests never touch real data."""
    memory_file = tmp_path / "memory.json"
    state_file = tmp_path / "state.json"
    execution_file = tmp_path / "execution_sessions.json"
    notifications_file = tmp_path / "notifications.json"
    results_file = tmp_path / "results.json"

    monkeypatch.setattr("services.memory.MEMORY_FILE", memory_file)
    monkeypatch.setattr("services.state.STATE_FILE", state_file)
    monkeypatch.setattr("services.execution.EXECUTION_SESSIONS_FILE", execution_file)
    monkeypatch.setattr("services.proactive.NOTIFICATIONS_FILE", notifications_file)
    monkeypatch.setattr("services.scheduler.RESULTS_FILE", results_file)

    # Clear caches to ensure perfect test isolation
    import services.memory
    import services.state
    import services.execution
    import services.proactive
    import event_timeline
    import services.vector_memory
    import services.scheduler

    services.memory._memory_store_cache = None
    services.state._state_store_cache = None
    services.execution._execution_store_cache = None
    services.proactive._notifications_store_cache = None
    event_timeline._timeline_store_cache = None
    services.vector_memory._fallback_store_cache = None
    services.vector_memory._chroma_client = None
    services.vector_memory._chroma_collection = None
    services.scheduler._results_store_cache = None

    yield {
        "memory": memory_file,
        "state": state_file,
        "execution": execution_file,
        "notifications": notifications_file,
        "results": results_file,
    }


@pytest.fixture
def user_id():
    return "test_user_001"


@pytest.fixture
def clean_memory(user_id):
    """Return a helper that seeds memory with given data."""
    from services.memory import save_user_memory

    def _seed(data: dict | None = None):
        save_user_memory(user_id, data or {})

    return _seed


@pytest.fixture
def clean_state(user_id):
    """Return a helper that seeds state with given data."""
    from services.state import update_user_state

    def _seed(data: dict | None = None):
        update_user_state(user_id, data or {})

    return _seed
