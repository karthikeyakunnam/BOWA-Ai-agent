"""Internal health diagnostics and validation check helpers for BOWA."""

import json
import logging
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from database import engine
from sqlalchemy.sql import text

from services.memory import read_memory_store, MEMORY_FILE
from services.state import _read_store, STATE_FILE
from services.execution import read_execution_sessions, EXECUTION_SESSIONS_FILE
from services.proactive import read_notifications_store, NOTIFICATIONS_FILE

logger = logging.getLogger(__name__)

# Global metrics tracker for scheduler
_health_data: dict[str, Any] = {
    "last_scheduler_run": None,
    "last_error": None
}
_health_lock = threading.Lock()

_websocket_count_provider = None


def register_websocket_provider(provider_fn) -> None:
    """Register a callback provider to get the current WebSocket connection count."""
    global _websocket_count_provider
    _websocket_count_provider = provider_fn


def setup_health_monitoring() -> None:
    """Wrap scheduler operations to track runtimes and capture background errors."""
    import services.scheduler

    original_run = services.scheduler.run_bowa_for_all_users

    def wrapped_run(*args, **kwargs):
        with _health_lock:
            _health_data["last_scheduler_run"] = datetime.now(timezone.utc).isoformat()
        try:
            return original_run(*args, **kwargs)
        except Exception as e:
            with _health_lock:
                _health_data["last_error"] = f"{type(e).__name__}: {str(e)}"
            raise e

    services.scheduler.run_bowa_for_all_users = wrapped_run


def check_memory_corruption() -> bool:
    """Validate memory.json structure and JSON encoding."""
    if not MEMORY_FILE.exists():
        return False
    try:
        with MEMORY_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return True
        for v in data.values():
            if not isinstance(v, dict):
                return True
        return False
    except Exception:
        return True


def check_db_connection() -> bool:
    """Validate SQLAlchemy engine connection works by pinging database."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.warning("Database connection failed: %s", e)
        return False


def get_system_health() -> dict[str, Any]:
    """Gather and return system health diagnostics."""
    # 1. Count active sessions
    active_sessions = 0
    try:
        sessions = read_execution_sessions()
        now = datetime.now(timezone.utc)
        for s in sessions.values():
            if s.get("active") and s.get("status") == "running":
                try:
                    start_time = datetime.fromisoformat(s.get("start_time", ""))
                    duration = s.get("duration", 25)
                    if now - start_time <= timedelta(minutes=duration):
                        active_sessions += 1
                except Exception:
                    pass
    except Exception as e:
        logger.error("Failed to read active sessions for health check: %s", e)

    # 2. Count active plans
    active_plans = 0
    try:
        states = _read_store()
        for state in states.values():
            plan = state.get("active_plan")
            if isinstance(plan, dict) and not plan.get("completed"):
                active_plans += 1
    except Exception as e:
        logger.error("Failed to read active plans for health check: %s", e)

    # 3. Count unique users
    users_count = 0
    try:
        memory_keys = set(read_memory_store().keys())
        state_keys = set(_read_store().keys())
        exec_keys = set(read_execution_sessions().keys())
        unique_users = memory_keys.union(state_keys).union(exec_keys)
        users_count = len(unique_users)
    except Exception as e:
        logger.error("Failed to read users count for health check: %s", e)

    # 4. Count pending/stored notifications
    notifications_pending = 0
    try:
        notifications_store = read_notifications_store()
        notifications_pending = sum(len(notifs) for notifs in notifications_store.values())
    except Exception as e:
        logger.error("Failed to read notifications count for health check: %s", e)

    # 5. Check if scheduler is running
    scheduler_running = False
    try:
        import services.scheduler
        thread = services.scheduler._scheduler_thread
        scheduler_running = thread is not None and thread.is_alive()
    except Exception as e:
        logger.error("Failed to check scheduler status: %s", e)

    # 6. Validate memory corruption
    memory_corruption_detected = check_memory_corruption()

    # 7. Check database connection
    db_connected = check_db_connection()

    # 8. WebSocket connections
    ws_connections = 0
    if _websocket_count_provider:
        try:
            ws_connections = _websocket_count_provider()
        except Exception as e:
            logger.error("Failed to get websocket connection count: %s", e)

    with _health_lock:
        last_sched = _health_data["last_scheduler_run"]
        last_err = _health_data["last_error"]

    return {
        "active_sessions": active_sessions,
        "active_plans": active_plans,
        "users": users_count,
        "notifications_pending": notifications_pending,
        "scheduler_running": scheduler_running,
        "memory_corruption_detected": memory_corruption_detected,
        "db_connected": db_connected,
        "websocket_connections": ws_connections,
        "last_scheduler_run": last_sched,
        "last_error": last_err
    }
