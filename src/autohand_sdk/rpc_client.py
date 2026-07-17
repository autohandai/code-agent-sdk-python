"""JSON-RPC client for communicating with the Autohand CLI subprocess."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Any, cast

from autohand_sdk.errors import TransportError
from autohand_sdk.transport import Transport, TransportOptions
from autohand_sdk.types import (
    SDKConfig,
    SkillReference,
    get_skill_name,
    get_skill_path,
    validate_provider_config,
)

logger = logging.getLogger(__name__)

RPC_METHODS = {
    "prompt": "autohand.prompt",
    "abort": "autohand.abort",
    "permission_response": "autohand.permissionResponse",
    "get_state": "autohand.getState",
    "get_messages": "autohand.getMessages",
    "get_supported_models": "autohand.getSupportedModels",
    "get_supported_commands": "autohand.getSupportedCommands",
    "set_model": "autohand.modelSet",
    "apply_flag_settings": "autohand.applyFlagSettings",
    "get_account_info": "autohand.getAccountInfo",
    "autoresearch_start": "autohand.autoresearch.start",
    "autoresearch_status": "autohand.autoresearch.status",
    "autoresearch_stop": "autohand.autoresearch.stop",
    "autoresearch_history": "autohand.autoresearch.history",
    "autoresearch_replay": "autohand.autoresearch.replay",
    "autoresearch_rescore": "autohand.autoresearch.rescore",
    "autoresearch_compare": "autohand.autoresearch.compare",
    "autoresearch_pareto": "autohand.autoresearch.pareto",
    "autoresearch_pin": "autohand.autoresearch.pin",
    "autoresearch_prune": "autohand.autoresearch.prune",
}

NOTIFICATION_EVENT_TYPES = {
    "autohand.agentStart": "agent_start",
    "autohand.agentEnd": "agent_end",
    "autohand.turnStart": "turn_start",
    "autohand.turnEnd": "turn_end",
    "autohand.messageStart": "message_start",
    "autohand.messageUpdate": "message_update",
    "autohand.messageEnd": "message_end",
    "autohand.toolStart": "tool_start",
    "autohand.toolUpdate": "tool_update",
    "autohand.toolEnd": "tool_end",
    "autohand.permissionRequest": "permission_request",
    "autohand.directoryAccessRequest": "directory_access_request",
    "autohand.error": "error",
    "autohand.hook.fileModified": "file_modified",
    "autohand.changesBatchStart": "changes_batch_start",
    "autohand.changesBatchUpdate": "changes_batch_update",
    "autohand.changesBatchEnd": "changes_batch_end",
    "autohand.autoresearch.start": "autoresearch",
    "autohand.autoresearch.status": "autoresearch",
    "autohand.autoresearch.pause": "autoresearch",
    "autohand.autoresearch.event": "autoresearch",
}

AUTORESEARCH_LIFECYCLE_PHASES = {
    "autohand.autoresearch.start": "start",
    "autohand.autoresearch.status": "status",
    "autohand.autoresearch.pause": "pause",
}

CAMEL_TO_SNAKE_KEYS = {
    "sessionId": "session_id",
    "turnId": "turn_id",
    "messageId": "message_id",
    "toolId": "tool_id",
    "toolName": "tool_name",
    "requestId": "request_id",
    "filePath": "file_path",
    "changeType": "change_type",
    "contextPercent": "context_percent",
    "messageCount": "message_count",
    "maxIterations": "max_iterations",
    "runsLogged": "runs_logged",
    "statusText": "status_text",
    "attemptId": "attempt_id",
    "bytesFreed": "bytes_freed",
    "remainingBytes": "remaining_bytes",
    "evaluatorMode": "evaluator_mode",
    "driftWarnings": "drift_warnings",
}


class RPCClient:
    """High-level JSON-RPC client for the Autohand CLI."""

    def __init__(self, config: SDKConfig | None = None) -> None:
        self.config = config if config is not None else SDKConfig.model_validate({})
        self._transport: Transport | None = None
        self._started = False
        self._event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._prompt_lock = asyncio.Lock()

        if self.config.provider is not None:
            validate_provider_config(self.config.provider, self.config)

        opts = self._build_transport_options()
        self._transport = Transport(opts)
        self._transport.on_notification("*", self._handle_notification)

    async def start(self) -> None:
        """Start the RPC client."""
        if self._started:
            return
        if not self._transport:
            raise RuntimeError("Transport not initialized")
        await self._transport.start()
        if self.config.startup_check and self._transport.is_running():
            try:
                await self._request(RPC_METHODS["get_state"], {})
            except Exception as exc:
                stderr = self._transport.stderr_tail
                await self._transport.stop()
                detail = f"\nCLI stderr:\n{stderr}" if stderr else ""
                raise TransportError(f"CLI startup check failed: {exc}{detail}") from exc
            finally:
                self._drain_event_queue()
        self._started = True

    async def stop(self) -> None:
        """Stop the RPC client."""
        if self._transport:
            await self._transport.stop()
        self._started = False

    async def initialize(self, config: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return current state.

        The CLI initializes itself when RPC mode starts. This method remains for
        compatibility with early SDK builds that exposed ``initialize()``.
        """
        return cast(dict[str, Any], await self._request(RPC_METHODS["get_state"], config or {}))

    async def prompt(self, params: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        """Send a prompt to the agent and stream SDK events."""
        async with self._prompt_lock:
            self._drain_event_queue()
            request_task = asyncio.create_task(self._request(RPC_METHODS["prompt"], params))
            seen_events = False

            while not request_task.done():
                get_event = asyncio.create_task(self._event_queue.get())
                done, pending = await asyncio.wait(
                    {request_task, get_event},
                    return_when=asyncio.FIRST_COMPLETED,
                )

                if get_event in done:
                    seen_events = True
                    yield get_event.result()
                else:
                    get_event.cancel()
                    with suppress(asyncio.CancelledError):
                        await get_event

                for task in pending:
                    if task is not request_task:
                        task.cancel()
                        with suppress(asyncio.CancelledError):
                            await task

            while not self._event_queue.empty():
                seen_events = True
                yield self._event_queue.get_nowait()

            result = await request_task

            if not seen_events and isinstance(result, dict):
                session_id = result.get("sessionId") or result.get("session_id") or ""
                yield {"type": "agent_start", "session_id": session_id}
                if result.get("content"):
                    yield {"type": "message_end", "content": result["content"]}
                yield {"type": "agent_end", "session_id": session_id, "reason": "completed"}

    async def events(self) -> AsyncIterator[dict[str, Any]]:
        """Stream all CLI notifications as SDK event dictionaries."""
        while True:
            yield await self._event_queue.get()

    async def abort(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Abort the current operation."""
        return cast(dict[str, Any], await self._request(RPC_METHODS["abort"], params or {}))

    async def respond_to_permission(self, params: dict[str, Any]) -> dict[str, Any]:
        """Respond to a permission request."""
        return cast(dict[str, Any], await self._request(RPC_METHODS["permission_response"], params))

    async def get_state(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Get the agent state."""
        return cast(dict[str, Any], await self._request(RPC_METHODS["get_state"], params or {}))

    async def get_messages(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Get messages from the agent."""
        return cast(dict[str, Any], await self._request(RPC_METHODS["get_messages"], params or {}))

    async def get_models(self) -> dict[str, Any]:
        """Get supported models."""
        return cast(dict[str, Any], await self._request(RPC_METHODS["get_supported_models"], {}))

    async def get_agents(self) -> dict[str, Any]:
        """Get supported command names.

        The current CLI exposes commands rather than an agent registry over RPC.
        The method name is kept for backward compatibility.
        """
        return cast(dict[str, Any], await self._request(RPC_METHODS["get_supported_commands"], {}))

    async def set_model(self, model: str) -> dict[str, Any]:
        """Set the active model."""
        return cast(dict[str, Any], await self._request(RPC_METHODS["set_model"], {"model": model}))

    async def set_agent(self, agent: str) -> dict[str, Any]:
        """Set the active agent flag when supported by the CLI."""
        return cast(
            dict[str, Any],
            await self._request(
                RPC_METHODS["apply_flag_settings"],
                {"settings": {"agent": agent}},
            ),
        )

    async def set_temperature(self, temperature: float) -> dict[str, Any]:
        """Set the active sampling temperature."""
        return cast(
            dict[str, Any],
            await self._request(
                RPC_METHODS["apply_flag_settings"],
                {"settings": {"temperature": temperature}},
            ),
        )

    async def get_account_info(self) -> dict[str, Any]:
        """Get account info."""
        return cast(dict[str, Any], await self._request(RPC_METHODS["get_account_info"], {}))

    async def save_session(self) -> dict[str, Any]:
        """Return state after asking the CLI to persist sessions via startup flags.

        The current CLI does not expose a dedicated save-session RPC method.
        """
        return cast(dict[str, Any], await self._request(RPC_METHODS["get_state"], {}))

    async def start_autoresearch(self, params: dict[str, Any]) -> dict[str, Any]:
        """Initialize or resume an autoresearch session."""
        return cast(dict[str, Any], await self._request(RPC_METHODS["autoresearch_start"], params))

    async def get_autoresearch_status(self) -> dict[str, Any]:
        """Read the current autoresearch lifecycle and ledger summary."""
        return cast(dict[str, Any], await self._request(RPC_METHODS["autoresearch_status"], {}))

    async def stop_autoresearch(self) -> dict[str, Any]:
        """Pause autoresearch without deleting its persisted state."""
        return cast(dict[str, Any], await self._request(RPC_METHODS["autoresearch_stop"], {}))

    async def get_autoresearch_history(self) -> dict[str, Any]:
        """List immutable autoresearch attempts."""
        return cast(dict[str, Any], await self._request(RPC_METHODS["autoresearch_history"], {}))

    async def replay_autoresearch(self, params: dict[str, Any]) -> dict[str, Any]:
        """Replay one attempt with its original or the current evaluator."""
        return cast(dict[str, Any], await self._request(RPC_METHODS["autoresearch_replay"], params))

    async def rescore_autoresearch(self, params: dict[str, Any]) -> dict[str, Any]:
        """Apply current decision policy to stored measurements."""
        return cast(dict[str, Any], await self._request(RPC_METHODS["autoresearch_rescore"], params))

    async def compare_autoresearch(self, params: dict[str, Any]) -> dict[str, Any]:
        """Compare two autoresearch attempts."""
        return cast(dict[str, Any], await self._request(RPC_METHODS["autoresearch_compare"], params))

    async def get_autoresearch_pareto(self) -> dict[str, Any]:
        """List constraint-passing non-dominated attempts."""
        return cast(dict[str, Any], await self._request(RPC_METHODS["autoresearch_pareto"], {}))

    async def pin_autoresearch(self, params: dict[str, Any]) -> dict[str, Any]:
        """Protect or release an attempt's artifacts from pruning."""
        return cast(dict[str, Any], await self._request(RPC_METHODS["autoresearch_pin"], params))

    async def prune_autoresearch(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Preview or explicitly apply autoresearch artifact pruning."""
        return cast(dict[str, Any], await self._request(RPC_METHODS["autoresearch_prune"], params or {}))

    async def _request(self, method: str, params: dict[str, Any]) -> Any:
        """Send a request to the transport."""
        if not self._transport:
            raise RuntimeError("Transport not initialized")
        return await self._transport.request(method, params)

    def is_running(self) -> bool:
        """Check if the client is running."""
        return self._transport is not None and self._transport.is_running()

    def _build_transport_options(self) -> TransportOptions:
        """Translate SDKConfig into CLI transport options."""
        opts = TransportOptions(
            cwd=self.config.cwd,
            cli_path=self.config.cli_path,
            debug=self.config.debug or False,
            timeout=self.config.timeout or 300000,
            auto_mode=self.config.auto_mode,
            unrestricted=self.config.unrestricted,
            auto_skill=self.config.auto_skill,
            model=self.config.model,
            temperature=self.config.temperature,
            max_iterations=self.config.max_iterations,
            max_runtime=self.config.max_runtime,
            max_cost=self.config.max_cost,
            sys_prompt=self.config.sys_prompt,
            append_sys_prompt=self.config.append_sys_prompt,
            yolo=self.config.yolo,
            yolo_timeout=self.config.yolo_timeout,
            add_dir=self._merge_lists(self.config.add_dir, self.config.additional_directories),
            extra_args=self.config.extra_args or [],
            permission_mode=self.config.permission_mode,
            persist_session=self.config.persist_session,
            session_id=self.config.session_id,
            resume=self.config.resume,
            continue_session=self.config.continue_,
            context_compact=self.config.context_compact,
            copy_skill_files=self.config.copy_skill_files,
            provider=self.config.provider.value if self.config.provider else None,
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            autohand_ai_plan=self.config.autohand_ai_plan,
        )

        if self.config.session:
            if self.config.session.persist_session is not None:
                opts.persist_session = self.config.session.persist_session
            if self.config.session.session_id is not None:
                opts.session_id = self.config.session.session_id
            if self.config.session.resume is not None:
                opts.resume = self.config.session.resume
            if self.config.session.continue_ is not None:
                opts.continue_session = self.config.session.continue_
            opts.session_path = self.config.session.session_path
            opts.auto_save_interval = self.config.session.auto_save_interval

        if self.config.context:
            if self.config.context.context_compact is not None:
                opts.context_compact = self.config.context.context_compact
            opts.max_tokens = self.config.context.max_tokens
            opts.compression_threshold = self.config.context.compression_threshold
            opts.summarization_threshold = self.config.context.summarization_threshold

        if self.config.permissions:
            opts.permission_mode = self.config.permissions.mode
            opts.permission_allow_list = self.config.permissions.allow_list
            opts.permission_deny_list = self.config.permissions.deny_list

        skill_refs: list[SkillReference] = (
            self.config.skill_refs
            if self.config.skill_refs is not None
            else (self.config.skills.skills if self.config.skills else [])
        )
        opts.skills, opts.skill_files = self._process_skill_refs(skill_refs)

        if self.config.skills:
            if self.config.skills.auto_skill is not None:
                opts.auto_skill = self.config.skills.auto_skill
            opts.skill_sources = [
                source.name if source.name else source.path or source.url or ""
                for source in self.config.skills.sources
            ]
            opts.skill_sources = [source for source in opts.skill_sources if source]
            opts.install_missing_skills = self.config.skills.install_missing

        if self.config.env_vars:
            env_dict = self.config.env_vars.model_dump(by_alias=True, exclude_none=True)
            opts.env_vars = {k: v for k, v in env_dict.items() if v is not None}

        return opts

    def _drain_event_queue(self) -> None:
        """Discard queued notifications from earlier compatibility probes."""
        while not self._event_queue.empty():
            with suppress(asyncio.QueueEmpty):
                self._event_queue.get_nowait()

    def _process_skill_refs(self, refs: list[SkillReference]) -> tuple[list[str], list[str]]:
        """Return skill names for CLI activation and file paths to copy first."""
        names: list[str] = []
        files: list[str] = []
        for ref in refs:
            name = get_skill_name(ref)
            path = get_skill_path(ref)
            if path is not None:
                files.append(path)
            names.append(name)
        return names, files

    def _merge_lists(
        self,
        primary: list[str] | None,
        secondary: list[str] | None,
    ) -> list[str]:
        """Merge optional config lists without duplicates while preserving order."""
        merged: list[str] = []
        for value in [*(primary or []), *(secondary or [])]:
            if value not in merged:
                merged.append(value)
        return merged

    def _handle_notification(self, params: dict[str, Any]) -> None:
        """Convert a JSON-RPC notification into SDK event dictionaries."""
        method = params.get("_method")
        if not isinstance(method, str):
            return

        event_type = NOTIFICATION_EVENT_TYPES.get(method)
        if event_type is None:
            return

        event = self._notification_to_event(event_type, params)
        self._event_queue.put_nowait(event)

        if method == "autohand.turnEnd":
            self._event_queue.put_nowait(
                {
                    "type": "agent_end",
                    "session_id": event.get("session_id") or event.get("turn_id", ""),
                    "reason": "completed",
                    "timestamp": event.get("timestamp"),
                }
            )

    def _notification_to_event(self, event_type: str, params: dict[str, Any]) -> dict[str, Any]:
        """Normalize CLI notification params into a Python-friendly event dict."""
        method = params.get("_method")
        event = {k: v for k, v in params.items() if k != "_method"}
        for camel, snake in CAMEL_TO_SNAKE_KEYS.items():
            if camel in event and snake not in event:
                event[snake] = event[camel]
        event["type"] = event_type
        lifecycle_phase = AUTORESEARCH_LIFECYCLE_PHASES.get(method) if isinstance(method, str) else None
        if lifecycle_phase is not None:
            event["phase"] = lifecycle_phase
        return event
