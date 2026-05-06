"""Real-time event bus for BOWA.

Central event emitter that routes notifications and execution events to
connected WebSocket users.
"""

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

_manager = None
_loop: asyncio.AbstractEventLoop | None = None


def register_manager(manager: Any) -> None:
    """Register a WebSocket connection manager for event delivery."""
    global _manager, _loop
    _manager = manager

    try:
        _loop = asyncio.get_running_loop()
    except RuntimeError:
        try:
            _loop = asyncio.get_event_loop()
        except RuntimeError:
            _loop = None

    logger.info("bowa_event registered manager")


def emit_event(user_id: str, type: str, payload: dict[str, Any]) -> None:
    """Emit an event for a single user.

    Events are delivered to the current WebSocket connection if one is
    available. Delivery is queued on the application event loop.
    """
    if _manager is None or _loop is None:
        logger.warning(
            "bowa_event skipped no manager or loop user=%s type=%s",
            user_id,
            type,
        )
        return

    message = {
        "type": type,
        "payload": payload,
    }

    try:
        asyncio.run_coroutine_threadsafe(_manager.send(user_id, message), _loop)
        logger.info("bowa_event emitted type=%s user=%s", type, user_id)
    except Exception as exc:
        logger.warning(
            "bowa_event failed user=%s type=%s error=%s",
            user_id,
            type,
            exc,
        )
