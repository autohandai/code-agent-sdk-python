"""JSON-RPC client for communicating with the Autohand CLI subprocess."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import suppress
from typing import Any, Literal, cast

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
    "reset": "autohand.reset",
    "browser_handoff_create": "autohand.browserHandoff.create",
    "browser_handoff_attach": "autohand.browserHandoff.attach",
    "browser_handoff_attach_latest": "autohand.browserHandoff.attachLatest",
    "automode_start": "autohand.automode.start",
    "automode_status": "autohand.automode.status",
    "automode_pause": "autohand.automode.pause",
    "automode_resume": "autohand.automode.resume",
    "automode_cancel": "autohand.automode.cancel",
    "automode_get_log": "autohand.automode.getLog",
    "permission_response": "autohand.permissionResponse",
    "permission_acknowledged": "autohand.permissionAcknowledged",
    "directory_access_response": "autohand.directoryAccessResponse",
    "directory_access_acknowledged": "autohand.directoryAccessAcknowledged",
    "changes_decision": "autohand.changesDecision",
    "get_history": "autohand.getHistory",
    "get_session": "autohand.getSession",
    "session_attach": "autohand.session.attach",
    "yolo_set": "autohand.yoloSet",
    "yolo_set_compat": "autohand.yolo.set",
    "mcp_set_vscode_tools": "autohand.mcp.setVscodeTools",
    "mcp_invoke_response": "autohand.mcp.invokeResponse",
    "learn_recommend": "autohand.learn.recommend",
    "learn_update": "autohand.learn.update",
    "learn_generate": "autohand.learn.generate",
    "get_tools_registry": "autohand.getToolsRegistry",
    "set_context_compact": "autohand.setContextCompact",
    "get_state": "autohand.getState",
    "get_messages": "autohand.getMessages",
    "get_supported_models": "autohand.getSupportedModels",
    "get_supported_commands": "autohand.getSupportedCommands",
    "get_skills_registry": "autohand.getSkillsRegistry",
    "install_skill": "autohand.installSkill",
    "set_model": "autohand.modelSet",
    "set_plan_mode": "autohand.planModeSet",
    "apply_flag_settings": "autohand.applyFlagSettings",
    "get_account_info": "autohand.getAccountInfo",
    "mcp_list_servers": "autohand.mcp.listServers",
    "mcp_list_tools": "autohand.mcp.listTools",
    "mcp_get_server_configs": "autohand.mcp.getServerConfigs",
    "goal_get": "autohand.goal.get",
    "goal_create": "autohand.goal.create",
    "goal_update": "autohand.goal.update",
    "goal_clear": "autohand.goal.clear",
    "goal_queue": "autohand.goal.queue",
    "goal_start_queued": "autohand.goal.startQueued",
    "goal_list_templates": "autohand.goal.listTemplates",
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
    "autohand.automode.iteration": "automode_iteration",
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
    "tokensUsed": "tokens_used",
    "tokensUsageStatus": "tokens_usage_status",
    "durationMs": "duration_ms",
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

EVENT_BACKLOG_LIMIT = 1_024
EventQueue = asyncio.Queue[dict[str, Any] | None]
ClientTerminationCallback = Callable[[BaseException], None]
PROMPT_CLEANUP_TIMEOUT_SECONDS = 2.0


class RPCClient:
    """High-level JSON-RPC client for the Autohand CLI."""

    def __init__(
        self,
        config: SDKConfig | None = None,
        *,
        termination_callback: ClientTerminationCallback | None = None,
    ) -> None:
        self.config = config if config is not None else SDKConfig.model_validate({})
        self._transport: Transport | None = None
        self._started = False
        # ``_event_queue`` remains as a compatibility/debug backlog. Live
        # consumers use dedicated queues so they cannot steal each other's
        # notifications.
        self._event_queue: EventQueue = asyncio.Queue(maxsize=EVENT_BACKLOG_LIMIT)
        self._event_subscribers: set[EventQueue] = set()
        self._event_streams_closed = False
        self._prompt_event_queue: EventQueue | None = None
        self._prompt_lock = asyncio.Lock()
        self._lifecycle_lock = asyncio.Lock()
        self._termination_callback = termination_callback

        if self.config.provider is not None:
            validate_provider_config(self.config.provider, self.config)

        opts = self._build_transport_options()
        self._transport = Transport(opts)
        self._transport.on_notification("*", self._handle_notification)
        self._transport.on_termination(self._handle_termination)

    async def start(self) -> None:
        """Start the RPC client."""
        async with self._lifecycle_lock:
            if self._started and self.is_running():
                return
            self._started = False
            if not self._transport:
                raise RuntimeError("Transport not initialized")
            await self._transport.start()
            if not self._transport.is_running():
                raise TransportError("CLI transport stopped during startup")
            self._event_streams_closed = False
            if self.config.startup_check:
                try:
                    await self._request(RPC_METHODS["get_state"], {})
                except Exception as exc:
                    stderr = self._transport.stderr_tail
                    await self._transport.stop()
                    self._close_event_streams(exc)
                    detail = f"\nCLI stderr:\n{stderr}" if stderr else ""
                    raise TransportError(f"CLI startup check failed: {exc}{detail}") from exc
                finally:
                    self._drain_event_queue()
            if not self._transport.is_running():
                raise TransportError("CLI transport stopped during startup")
            self._started = True

    async def stop(self) -> None:
        """Stop the RPC client."""
        async with self._lifecycle_lock:
            try:
                if self._transport:
                    await self._transport.stop()
            finally:
                self._started = False
                self._close_event_streams()

    async def initialize(self, config: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return current state.

        The CLI initializes itself when RPC mode starts. This method remains for
        compatibility with early SDK builds that exposed ``initialize()``.
        """
        return cast(dict[str, Any], await self._request(RPC_METHODS["get_state"], config or {}))

    async def prompt(self, params: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        """Send a prompt to the agent and stream SDK events."""
        async with self._prompt_lock:
            prompt_queue: EventQueue = asyncio.Queue(maxsize=EVENT_BACKLOG_LIMIT)
            self._prompt_event_queue = prompt_queue
            request_task: asyncio.Task[Any] | None = None
            get_event: asyncio.Task[dict[str, Any] | None] | None = None
            seen_events = False
            terminal_event_seen = False
            request_result: Any = None
            request_acknowledged = False
            request_failed = False
            try:
                request_task = asyncio.create_task(self._request(RPC_METHODS["prompt"], params))

                while not terminal_event_seen:
                    get_event = asyncio.create_task(prompt_queue.get())
                    if not request_acknowledged:
                        done, _ = await asyncio.wait(
                            {request_task, get_event},
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        if request_task in done:
                            try:
                                request_result = await request_task
                            except BaseException:
                                request_failed = True
                                raise
                            request_acknowledged = True

                            if (
                                not seen_events
                                and isinstance(request_result, dict)
                                and (
                                    request_result.get("content") is not None
                                    or request_result.get("sessionId") is not None
                                    or request_result.get("session_id") is not None
                                )
                                and not get_event.done()
                            ):
                                get_event.cancel()
                                with suppress(asyncio.CancelledError):
                                    await get_event
                                get_event = None
                                session_id = (
                                    request_result.get("sessionId")
                                    or request_result.get("session_id")
                                    or ""
                                )
                                yield {"type": "agent_start", "session_id": session_id}
                                if request_result.get("content"):
                                    yield {
                                        "type": "message_end",
                                        "content": request_result["content"],
                                    }
                                yield {
                                    "type": "agent_end",
                                    "session_id": session_id,
                                    "reason": "completed",
                                }
                                seen_events = True
                                terminal_event_seen = True
                                break

                            if get_event not in done:
                                get_event.cancel()
                                with suppress(asyncio.CancelledError):
                                    await get_event
                                get_event = None
                                continue
                    else:
                        await get_event

                    event = get_event.result()
                    get_event = None
                    if event is None:
                        raise TransportError("Prompt event stream closed")
                    seen_events = True
                    terminal_event_seen = event.get("type") == "agent_end"
                    yield event

                if not request_acknowledged:
                    request_result = await request_task
                    request_acknowledged = True

                if not seen_events and isinstance(request_result, dict):
                    session_id = (
                        request_result.get("sessionId") or request_result.get("session_id") or ""
                    )
                    yield {"type": "agent_start", "session_id": session_id}
                    if request_result.get("content"):
                        yield {"type": "message_end", "content": request_result["content"]}
                    yield {
                        "type": "agent_end",
                        "session_id": session_id,
                        "reason": "completed",
                    }
            finally:
                try:
                    if get_event is not None and not get_event.done():
                        get_event.cancel()
                        with suppress(asyncio.CancelledError):
                            await get_event
                    if request_task is not None:
                        try:
                            if not terminal_event_seen and not request_failed:
                                await self._settle_abandoned_prompt(prompt_queue)
                        finally:
                            if not request_task.done():
                                request_task.cancel()
                            with suppress(asyncio.CancelledError, Exception):
                                await request_task
                finally:
                    if self._prompt_event_queue is prompt_queue:
                        self._prompt_event_queue = None

    async def _settle_abandoned_prompt(self, prompt_queue: EventQueue) -> None:
        """Abort an accepted background turn and wait for its terminal event."""

        async def cleanup() -> bool:
            try:
                await self.abort()
            except Exception:
                return False
            while True:
                event = await prompt_queue.get()
                if event is None:
                    return False
                if event.get("type") == "agent_end":
                    return True

        try:
            settled = await asyncio.wait_for(cleanup(), timeout=PROMPT_CLEANUP_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            settled = False
        if not settled:
            await self.stop()

    async def events(self) -> AsyncIterator[dict[str, Any]]:
        """Stream all CLI notifications as SDK event dictionaries."""
        if self._event_streams_closed:
            return
        queue: EventQueue = asyncio.Queue(maxsize=EVENT_BACKLOG_LIMIT)
        if not self._event_subscribers:
            while not self._event_queue.empty():
                self._put_bounded(queue, self._event_queue.get_nowait())
        self._event_subscribers.add(queue)
        try:
            while True:
                event = await queue.get()
                if event is None:
                    return
                yield event
        finally:
            self._event_subscribers.discard(queue)

    async def abort(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Abort the current operation."""
        return cast(dict[str, Any], await self._request(RPC_METHODS["abort"], params or {}))

    async def reset(self) -> dict[str, Any]:
        """Reset the conversation context and return the new session ID."""
        return cast(dict[str, Any], await self._request(RPC_METHODS["reset"], {}))

    async def create_browser_handoff(
        self,
        extension_id: str | None = None,
        install_url: str | None = None,
    ) -> dict[str, Any]:
        """Create a browser handoff for the active session."""
        params: dict[str, Any] = {}
        if extension_id is not None:
            params["extensionId"] = extension_id
        if install_url is not None:
            params["installUrl"] = install_url
        return cast(
            dict[str, Any],
            await self._request(RPC_METHODS["browser_handoff_create"], params),
        )

    async def attach_browser_handoff(self, token: str) -> dict[str, Any]:
        """Consume a browser handoff token and attach its session."""
        return cast(
            dict[str, Any],
            await self._request(RPC_METHODS["browser_handoff_attach"], {"token": token}),
        )

    async def attach_latest_browser_handoff(self) -> dict[str, Any]:
        """Attach the newest pending browser handoff."""
        return cast(
            dict[str, Any],
            await self._request(RPC_METHODS["browser_handoff_attach_latest"], {}),
        )

    async def start_automode(  # noqa: PLR0913 - mirrors the CLI RPC contract
        self,
        prompt: str,
        *,
        max_iterations: int | None = None,
        completion_promise: str | None = None,
        use_worktree: bool | None = None,
        checkpoint_interval: int | None = None,
        max_runtime: int | float | None = None,
        max_cost: int | float | None = None,
    ) -> dict[str, Any]:
        """Start an autonomous execution session."""
        params: dict[str, Any] = {"prompt": prompt}
        optional = {
            "maxIterations": max_iterations,
            "completionPromise": completion_promise,
            "useWorktree": use_worktree,
            "checkpointInterval": checkpoint_interval,
            "maxRuntime": max_runtime,
            "maxCost": max_cost,
        }
        params.update({key: value for key, value in optional.items() if value is not None})
        return cast(
            dict[str, Any],
            await self._request(RPC_METHODS["automode_start"], params),
        )

    async def get_automode_status(self) -> dict[str, Any]:
        """Get the current autonomous execution status."""
        return cast(
            dict[str, Any],
            await self._request(RPC_METHODS["automode_status"], {}),
        )

    async def pause_automode(self) -> dict[str, Any]:
        """Pause the active autonomous execution session."""
        return cast(
            dict[str, Any],
            await self._request(RPC_METHODS["automode_pause"], {}),
        )

    async def resume_automode(self) -> dict[str, Any]:
        """Resume a paused autonomous execution session."""
        return cast(
            dict[str, Any],
            await self._request(RPC_METHODS["automode_resume"], {}),
        )

    async def cancel_automode(self, reason: str | None = None) -> dict[str, Any]:
        """Cancel the active autonomous execution session."""
        params = {} if reason is None else {"reason": reason}
        return cast(
            dict[str, Any],
            await self._request(RPC_METHODS["automode_cancel"], params),
        )

    async def get_automode_log(self, limit: int | None = None) -> dict[str, Any]:
        """Get auto-mode iteration log entries."""
        params = {} if limit is None else {"limit": limit}
        return cast(
            dict[str, Any],
            await self._request(RPC_METHODS["automode_get_log"], params),
        )

    async def respond_to_permission(self, params: dict[str, Any]) -> dict[str, Any]:
        """Respond to a permission request."""
        return cast(dict[str, Any], await self._request(RPC_METHODS["permission_response"], params))

    async def acknowledge_permission(self, request_id: str) -> dict[str, Any]:
        """Acknowledge receipt of a permission request before deciding it."""
        return cast(
            dict[str, Any],
            await self._request(
                RPC_METHODS["permission_acknowledged"],
                {"requestId": request_id},
            ),
        )

    async def respond_to_directory_access(self, request_id: str, granted: bool) -> dict[str, Any]:
        """Grant or deny a pending directory-access request."""
        return cast(
            dict[str, Any],
            await self._request(
                RPC_METHODS["directory_access_response"],
                {"requestId": request_id, "granted": granted},
            ),
        )

    async def acknowledge_directory_access(self, request_id: str) -> dict[str, Any]:
        """Acknowledge receipt of a directory-access request."""
        return cast(
            dict[str, Any],
            await self._request(
                RPC_METHODS["directory_access_acknowledged"],
                {"requestId": request_id},
            ),
        )

    async def decide_changes(self, params: dict[str, Any]) -> dict[str, Any]:
        """Apply or reject a batch of proposed file changes."""
        return cast(
            dict[str, Any],
            await self._request(RPC_METHODS["changes_decision"], params),
        )

    async def get_history(self, params: dict[str, Any]) -> dict[str, Any]:
        """Return paginated saved-session metadata."""
        return cast(
            dict[str, Any],
            await self._request(RPC_METHODS["get_history"], params),
        )

    async def get_session(self, session_id: str) -> dict[str, Any]:
        """Return one saved session with messages and workspace metadata."""
        return cast(
            dict[str, Any],
            await self._request(
                RPC_METHODS["get_session"],
                {"sessionId": session_id},
            ),
        )

    async def attach_session(self, session_id: str) -> dict[str, Any]:
        """Attach this RPC connection to a saved session."""
        return cast(
            dict[str, Any],
            await self._request(
                RPC_METHODS["session_attach"],
                {"sessionId": session_id},
            ),
        )

    async def set_yolo(self, params: dict[str, Any]) -> dict[str, Any]:
        """Set timed unrestricted mode through the canonical RPC."""
        return cast(dict[str, Any], await self._request(RPC_METHODS["yolo_set"], params))

    async def set_yolo_compat(self, params: dict[str, Any]) -> dict[str, Any]:
        """Set timed unrestricted mode through the legacy dotted RPC."""
        return cast(
            dict[str, Any],
            await self._request(RPC_METHODS["yolo_set_compat"], params),
        )

    async def set_vscode_mcp_tools(self, params: dict[str, Any]) -> dict[str, Any]:
        """Replace the CLI's VS Code-hosted MCP tool descriptors."""
        return cast(
            dict[str, Any],
            await self._request(RPC_METHODS["mcp_set_vscode_tools"], params),
        )

    async def respond_to_mcp_invocation(self, params: dict[str, Any]) -> dict[str, Any]:
        """Resolve a VS Code-hosted MCP invocation."""
        return cast(
            dict[str, Any],
            await self._request(RPC_METHODS["mcp_invoke_response"], params),
        )

    async def get_learning_recommendations(self, params: dict[str, Any]) -> dict[str, Any]:
        """Audit project skills and return relevant recommendations."""
        return cast(
            dict[str, Any],
            await self._request(RPC_METHODS["learn_recommend"], params),
        )

    async def update_learned_skills(self) -> dict[str, Any]:
        """Update installed project skills from their registry sources."""
        return cast(
            dict[str, Any],
            await self._request(RPC_METHODS["learn_update"], {}),
        )

    async def generate_skill(self, params: dict[str, Any]) -> dict[str, Any]:
        """Generate a reusable skill from the current project context."""
        return cast(
            dict[str, Any],
            await self._request(RPC_METHODS["learn_generate"], params),
        )

    async def get_tools_registry(self) -> dict[str, Any]:
        """Return built-in, meta, and extension tool registry entries."""
        return cast(
            dict[str, Any],
            await self._request(RPC_METHODS["get_tools_registry"], {}),
        )

    async def set_context_compact(self, enabled: bool) -> dict[str, Any]:
        """Enable or disable automatic context compaction."""
        return cast(
            dict[str, Any],
            await self._request(RPC_METHODS["set_context_compact"], {"enabled": enabled}),
        )

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

    async def get_skills_registry(self, force_refresh: bool | None = None) -> dict[str, Any]:
        """Get the community skill registry."""
        params = {} if force_refresh is None else {"forceRefresh": force_refresh}
        return cast(
            dict[str, Any],
            await self._request(RPC_METHODS["get_skills_registry"], params),
        )

    async def install_skill(
        self,
        skill_name: str,
        scope: Literal["user", "project"],
        force: bool | None = None,
    ) -> dict[str, Any]:
        """Install one community skill in user or project scope."""
        params: dict[str, Any] = {"skillName": skill_name, "scope": scope}
        if force is not None:
            params["force"] = force
        return cast(
            dict[str, Any],
            await self._request(RPC_METHODS["install_skill"], params),
        )

    async def list_mcp_servers(self) -> dict[str, Any]:
        """List known MCP servers and their connection status."""
        return cast(
            dict[str, Any],
            await self._request(RPC_METHODS["mcp_list_servers"], {}),
        )

    async def list_mcp_tools(self, server_name: str | None = None) -> dict[str, Any]:
        """List MCP tools, optionally filtering by server name."""
        params = {} if server_name is None else {"serverName": server_name}
        return cast(
            dict[str, Any],
            await self._request(RPC_METHODS["mcp_list_tools"], params),
        )

    async def get_mcp_server_configs(self) -> dict[str, Any]:
        """Get MCP server configurations from the CLI."""
        return cast(
            dict[str, Any],
            await self._request(RPC_METHODS["mcp_get_server_configs"], {}),
        )

    async def set_model(self, model: str) -> dict[str, Any]:
        """Set the active model."""
        return cast(dict[str, Any], await self._request(RPC_METHODS["set_model"], {"model": model}))

    async def set_plan_mode(self, enabled: bool) -> dict[str, Any]:
        """Enable or disable plan mode."""
        return cast(
            dict[str, Any],
            await self._request(RPC_METHODS["set_plan_mode"], {"enabled": enabled}),
        )

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

    async def apply_flag_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Merge settings into the CLI flag-settings layer."""
        return cast(
            dict[str, Any],
            await self._request(RPC_METHODS["apply_flag_settings"], {"settings": settings}),
        )

    async def get_account_info(self) -> dict[str, Any]:
        """Get account info."""
        return cast(dict[str, Any], await self._request(RPC_METHODS["get_account_info"], {}))

    async def save_session(self) -> dict[str, Any]:
        """Return state after asking the CLI to persist sessions via startup flags.

        The current CLI does not expose a dedicated save-session RPC method.
        """
        return cast(dict[str, Any], await self._request(RPC_METHODS["get_state"], {}))

    async def get_goal(self) -> dict[str, Any]:
        """Get the persistent-goal snapshot."""
        return cast(dict[str, Any], await self._request(RPC_METHODS["goal_get"], {}))

    async def create_goal(self, params: dict[str, Any]) -> dict[str, Any]:
        """Create a persistent goal."""
        return cast(dict[str, Any], await self._request(RPC_METHODS["goal_create"], params))

    async def update_goal(self, params: dict[str, Any]) -> dict[str, Any]:
        """Update the active persistent goal."""
        return cast(dict[str, Any], await self._request(RPC_METHODS["goal_update"], params))

    async def clear_goal(self) -> dict[str, Any]:
        """Clear the active persistent goal."""
        return cast(dict[str, Any], await self._request(RPC_METHODS["goal_clear"], {}))

    async def queue_goal(self, params: dict[str, Any]) -> dict[str, Any]:
        """Queue a persistent goal."""
        return cast(dict[str, Any], await self._request(RPC_METHODS["goal_queue"], params))

    async def start_queued_goal(self) -> dict[str, Any]:
        """Start the next queued persistent goal."""
        return cast(dict[str, Any], await self._request(RPC_METHODS["goal_start_queued"], {}))

    async def list_goal_templates(self) -> dict[str, Any] | list[dict[str, Any]]:
        """List available persistent-goal templates."""
        return cast(
            dict[str, Any] | list[dict[str, Any]],
            await self._request(RPC_METHODS["goal_list_templates"], {}),
        )

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
        return cast(
            dict[str, Any], await self._request(RPC_METHODS["autoresearch_rescore"], params)
        )

    async def compare_autoresearch(self, params: dict[str, Any]) -> dict[str, Any]:
        """Compare two autoresearch attempts."""
        return cast(
            dict[str, Any], await self._request(RPC_METHODS["autoresearch_compare"], params)
        )

    async def get_autoresearch_pareto(self) -> dict[str, Any]:
        """List constraint-passing non-dominated attempts."""
        return cast(dict[str, Any], await self._request(RPC_METHODS["autoresearch_pareto"], {}))

    async def pin_autoresearch(self, params: dict[str, Any]) -> dict[str, Any]:
        """Protect or release an attempt's artifacts from pruning."""
        return cast(dict[str, Any], await self._request(RPC_METHODS["autoresearch_pin"], params))

    async def prune_autoresearch(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Preview or explicitly apply autoresearch artifact pruning."""
        return cast(
            dict[str, Any], await self._request(RPC_METHODS["autoresearch_prune"], params or {})
        )

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
            auto_commit=self.config.auto_commit,
            bare=self.config.bare,
            idle_logout=self.config.idle_logout,
            model=self.config.model,
            temperature=self.config.temperature,
            max_iterations=self.config.max_iterations,
            max_runtime=self.config.max_runtime,
            max_cost=self.config.max_cost,
            sys_prompt=self.config.sys_prompt,
            system_prompt_file=self.config.system_prompt_file,
            append_sys_prompt=self.config.append_sys_prompt,
            append_system_prompt_file=self.config.append_system_prompt_file,
            display_language=self.config.display_language,
            mcp_config=self.config.mcp_config,
            agents=self.config.agents,
            plugin_dir=self.config.plugin_dir,
            yolo=self.config.yolo,
            yolo_timeout=self.config.yolo_timeout,
            add_dir=self._merge_lists(self.config.add_dir, self.config.additional_directories),
            extra_args=self.config.extra_args or [],
            permission_mode=self.config.permission_mode,
            persist_session=self.config.persist_session,
            session_id=self.config.session_id,
            resume=self.config.resume,
            continue_session=self.config.continue_,
            fork=self.config.fork,
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

        opts.agents_md_enable = self.config.agents_md_enable
        opts.agents_md_create = self.config.agents_md_create
        if self.config.agents_md:
            if self.config.agents_md.enable is not None:
                opts.agents_md_enable = self.config.agents_md.enable
            if self.config.agents_md.create is not None:
                opts.agents_md_create = self.config.agents_md.create
            opts.agents_md_path = self.config.agents_md.path
            opts.agents_md_auto_update = self.config.agents_md.auto_update

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
        self._publish_event(event)

        if method == "autohand.turnEnd":
            self._publish_event(
                {
                    "type": "agent_end",
                    "session_id": event.get("session_id") or event.get("turn_id", ""),
                    "reason": "completed",
                    "timestamp": event.get("timestamp"),
                }
            )

    def _publish_event(self, event: dict[str, Any]) -> None:
        """Broadcast one event without destructive competition between consumers."""
        if self._event_streams_closed:
            return
        if not self._event_subscribers:
            self._put_bounded(self._event_queue, event)
        if self._prompt_event_queue is not None:
            self._put_bounded(self._prompt_event_queue, event)
        for queue in tuple(self._event_subscribers):
            self._put_bounded(queue, event)

    @staticmethod
    def _put_bounded(queue: EventQueue, event: dict[str, Any] | None) -> None:
        if queue.full():
            with suppress(asyncio.QueueEmpty):
                queue.get_nowait()
        queue.put_nowait(event)

    def _handle_termination(self, error: BaseException) -> None:
        self._started = False
        self._close_event_streams(error)
        if self._termination_callback is not None:
            try:
                self._termination_callback(error)
            except Exception:
                logger.exception("Unhandled exception in client termination callback")

    def _close_event_streams(self, _error: BaseException | None = None) -> None:
        """Close every global event iterator and discard its queued notifications."""
        self._event_streams_closed = True
        self._drain_event_queue()
        if self._prompt_event_queue is not None:
            self._put_bounded(self._prompt_event_queue, None)
        for queue in tuple(self._event_subscribers):
            while not queue.empty():
                with suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            self._put_bounded(queue, None)
        self._event_subscribers.clear()

    def _notification_to_event(self, event_type: str, params: dict[str, Any]) -> dict[str, Any]:
        """Normalize CLI notification params into a Python-friendly event dict."""
        method = params.get("_method")
        event = {k: v for k, v in params.items() if k != "_method"}
        for camel, snake in CAMEL_TO_SNAKE_KEYS.items():
            if camel in event and snake not in event:
                event[snake] = event[camel]
        event["type"] = event_type
        lifecycle_phase = (
            AUTORESEARCH_LIFECYCLE_PHASES.get(method) if isinstance(method, str) else None
        )
        if lifecycle_phase is not None:
            event["phase"] = lifecycle_phase
        return event
