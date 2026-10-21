"""Lossless notification observation without replacing typed event handlers."""

from __future__ import annotations

import logging
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WireNotification:
    """Original CLI method and JSON parameters, including future payload shapes."""

    method: str
    params: Any


class NotificationObservers:
    """Ordered, independently removable notification subscriptions."""

    def __init__(self) -> None:
        self._callbacks: dict[object, Callable[[WireNotification], None]] = {}

    def subscribe(self, callback: Callable[[WireNotification], None]) -> Callable[[], None]:
        """Register a synchronous observer and return its unsubscribe function."""
        token = object()
        self._callbacks[token] = callback

        def unsubscribe() -> None:
            self._callbacks.pop(token, None)

        return unsubscribe

    def dispatch(self, notification: WireNotification) -> None:
        """Isolate each observer's mutations and errors from protocol delivery."""
        for callback in tuple(self._callbacks.values()):
            try:
                callback(WireNotification(notification.method, deepcopy(notification.params)))
            except Exception:
                logger.debug("Notification observer failed")
