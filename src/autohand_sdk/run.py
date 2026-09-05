"""Repeatable run results and independent event subscribers for an agent prompt."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import aclosing
from typing import TYPE_CHECKING, Literal, TypeVar, cast, overload
from uuid import uuid4

from autohand_sdk.errors import TransportError
from autohand_sdk.structured_output import parse_json_text
from autohand_sdk.types import AgentStep, PromptParams, RunResult, SDKEvent

if TYPE_CHECKING:
    from autohand_sdk.sdk import AutohandSDK

T = TypeVar("T")


class Run:
    """One lazy prompt with replayable events, repeatable waits, and scoped abort."""

    def __init__(self, sdk: AutohandSDK, params: PromptParams) -> None:
        self.id = f"run_{uuid4().hex}"
        self._sdk = sdk
        self._params = params
        self._task: asyncio.Task[RunResult] | None = None
        self._started = False
        self._aborted = False
        self._finished = False
        self._changed = asyncio.Event()
        self._events: list[SDKEvent] = []
        self._steps: list[AgentStep] = []
        self._text = ""
        self._status: Literal["completed", "aborted", "stopped"] = "completed"

    def _ensure_started(self) -> asyncio.Task[RunResult]:
        if self._task is None:
            self._task = asyncio.create_task(self._pump())
            # stream() callers need not also await wait() to retrieve failures.
            self._task.add_done_callback(
                lambda task: None if task.cancelled() else task.exception()
            )
        return self._task

    async def wait(self) -> RunResult:
        """Wait for the cached result; cancelling one waiter leaves other readers intact."""
        return await asyncio.shield(self._ensure_started())

    async def stream(self) -> AsyncIterator[SDKEvent]:
        """Replay buffered events, then receive live events through completion."""
        task = self._ensure_started()
        index = 0
        while True:
            while index < len(self._events):
                event = self._events[index]
                index += 1
                yield event
            if self._finished:
                await asyncio.shield(task)
                return
            self._changed.clear()
            await self._changed.wait()

    async def abort(self) -> None:
        """Cancel this run and settle its turn, including a pending host predicate."""
        if self._finished:
            return
        already_aborted = self._aborted
        self._aborted = True
        task = self._ensure_started()
        if self._started and not already_aborted:
            task.cancel()
        await asyncio.shield(task)

    @overload
    async def json(self, *, validate: Callable[[object], T]) -> T: ...

    @overload
    async def json(self, *, validate: None = None) -> object: ...

    async def json(self, *, validate: Callable[[object], T] | None = None) -> T | object:
        """Parse final JSON, optionally validating with a callable or Pydantic model."""
        value = parse_json_text((await self.wait()).text)
        return validate(value) if validate is not None else value

    async def _pump(self) -> RunResult:
        self._started = True
        try:
            if not self._aborted:
                async with aclosing(self._sdk._stream_prompt(self._params)) as stream:
                    async for event in stream:
                        self._record(event)
        except asyncio.CancelledError:
            if not self._aborted:
                raise
        finally:
            self._finished = True
            self._changed.set()
        return RunResult(
            id=self.id,
            status="aborted" if self._aborted else self._status,
            text=self._text,
            events=self._events.copy(),
            steps=self._steps.copy(),
        )

    def _record(self, event: SDKEvent) -> None:
        self._events.append(event)
        event_type = event.get("type")
        if event_type == "message_update":
            self._text += str(event.get("delta") or "")
        elif event_type == "message_end":
            self._text = str(event.get("content") or self._text)
        elif event_type == "step_end":
            self._steps.append(AgentStep.model_validate(event["step"]))
        elif event_type == "agent_end":
            reason = event.get("reason") or "completed"
            if reason not in ("completed", "aborted", "stopped"):
                raise TransportError(f"Agent turn ended with reason: {reason}")
            self._status = cast(Literal["completed", "aborted", "stopped"], reason)
        self._changed.set()
