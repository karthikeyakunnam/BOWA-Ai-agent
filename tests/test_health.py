"""Tests for BOWA internal health diagnostics and system-health endpoint."""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from main import app
from health import (
    check_memory_corruption,
    check_db_connection,
    get_system_health,
    register_websocket_provider,
)


@pytest.fixture
def client():
    return TestClient(app)


def test_check_memory_corruption_clean(tmp_path, monkeypatch):
    """Clean memory file should not report corruption."""
    from services.memory import save_user_memory
    memory_file = tmp_path / "memory.json"
    monkeypatch.setattr("services.memory.MEMORY_FILE", memory_file)
    monkeypatch.setattr("health.MEMORY_FILE", memory_file)

    # Clean empty/none state
    assert check_memory_corruption() is False

    # Seed valid memory
    save_user_memory("user_1", {"goal": "study"})
    assert check_memory_corruption() is False


def test_check_memory_corruption_malformed(tmp_path, monkeypatch):
    """Malformed or invalid memory structure should report corruption."""
    memory_file = tmp_path / "memory.json"
    monkeypatch.setattr("services.memory.MEMORY_FILE", memory_file)
    monkeypatch.setattr("health.MEMORY_FILE", memory_file)

    # 1. Invalid JSON syntax
    memory_file.write_text("invalid json format {", encoding="utf-8")
    assert check_memory_corruption() is True

    # 2. Invalid schema (not a dict)
    memory_file.write_text("[\"item1\", \"item2\"]", encoding="utf-8")
    assert check_memory_corruption() is True

    # 3. Invalid user value (not a dict)
    memory_file.write_text("{\"user_1\": \"not_a_dict_value\"}", encoding="utf-8")
    assert check_memory_corruption() is True


@patch("health.engine")
def test_check_db_connection(mock_engine):
    """DB connection check pings successfully or handles failure."""
    # 1. Successful query
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn
    assert check_db_connection() is True

    # 2. Connection failure
    mock_engine.connect.side_effect = Exception("DB Connection Timeout")
    assert check_db_connection() is False


def test_get_system_health_structure(tmp_path, monkeypatch):
    """get_system_health should return dict with all required BOWA diagnostics."""
    memory_file = tmp_path / "memory.json"
    state_file = tmp_path / "state.json"
    execution_file = tmp_path / "execution_sessions.json"
    notifications_file = tmp_path / "notifications.json"

    monkeypatch.setattr("services.memory.MEMORY_FILE", memory_file)
    monkeypatch.setattr("health.MEMORY_FILE", memory_file)
    monkeypatch.setattr("services.state.STATE_FILE", state_file)
    monkeypatch.setattr("health.STATE_FILE", state_file)
    monkeypatch.setattr("services.execution.EXECUTION_SESSIONS_FILE", execution_file)
    monkeypatch.setattr("health.EXECUTION_SESSIONS_FILE", execution_file)
    monkeypatch.setattr("services.proactive.NOTIFICATIONS_FILE", notifications_file)
    monkeypatch.setattr("health.NOTIFICATIONS_FILE", notifications_file)

    # Seed mock provider for WebSocket connections count
    register_websocket_provider(lambda: 3)

    health = get_system_health()

    assert "active_sessions" in health
    assert "active_plans" in health
    assert "users" in health
    assert "notifications_pending" in health
    assert "scheduler_running" in health
    assert "memory_corruption_detected" in health
    assert "db_connected" in health
    assert "websocket_connections" in health
    assert "last_scheduler_run" in health
    assert "last_error" in health

    assert health["websocket_connections"] == 3


def test_system_health_endpoint(client):
    """GET /system-health should return 200 and valid JSON diagnostics."""
    response = client.get("/system-health")
    assert response.status_code == 200
    
    data = response.json()
    assert "active_sessions" in data
    assert "active_plans" in data
    assert "users" in data
    assert "notifications_pending" in data
    assert "scheduler_running" in data
    assert "memory_corruption_detected" in data
    assert "db_connected" in data
    assert "websocket_connections" in data
