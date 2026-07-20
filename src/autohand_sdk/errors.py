"""Exception types raised by the Autohand SDK."""

from __future__ import annotations

from typing import Any


class AutohandSDKError(RuntimeError):
    """Base class for SDK errors."""


class TransportError(AutohandSDKError):
    """Raised when the CLI transport cannot send or receive RPC messages."""


class TransportNotStartedError(TransportError):
    """Raised when an RPC request is attempted before the transport starts."""


class RPCError(AutohandSDKError):
    """Raised when the CLI returns a JSON-RPC error response."""

    def __init__(self, message: str, *, code: int | None = None, data: Any | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.data = data


class RequestTimeoutError(TransportError, TimeoutError):
    """Raised when a JSON-RPC request does not receive a response in time."""
