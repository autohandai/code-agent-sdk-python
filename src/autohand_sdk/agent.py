"""High-level agent facade for command runs and persistent goals."""

from __future__ import annotations

from typing import Any, Literal

from autohand_sdk.sdk import AutohandSDK
from autohand_sdk.types import (
    AutomodeCancelResult,
    AutomodeGetLogResult,
    AutomodeOperationResult,
    AutomodeResumeResult,
    AutomodeStartResult,
    AutomodeStatusResult,
    BrowserHandoffAttachLatestResult,
    BrowserHandoffAttachResult,
    BrowserHandoffCreateResult,
    ChangesDecisionAction,
    ChangesDecisionResult,
    DirectoryAccessAcknowledgedResult,
    DirectoryAccessResponseResult,
    GetHistoryResult,
    GetSessionResult,
    GetSkillsRegistryResult,
    GoalMutationRPCResult,
    GoalSnapshotResult,
    GoalTemplatesResult,
    InstallSkillResult,
    McpGetServerConfigsResult,
    McpInvokeResponseResult,
    McpListServersResult,
    McpListToolsResult,
    McpSetVscodeToolsResult,
    PermissionAcknowledgedResult,
    PromptResult,
    ResetResult,
    SDKConfig,
    SessionAttachResult,
    UpdateGoalParams,
    VscodeMcpToolDescriptor,
    YoloSetResult,
)


class Agent:
    """Convenience facade over a started :class:`AutohandSDK` session."""

    def __init__(self, sdk: AutohandSDK) -> None:
        self._sdk = sdk

    @classmethod
    async def create(
        cls,
        config: SDKConfig | None = None,
        **kwargs: Any,
    ) -> Agent:
        """Create and start an agent session."""
        sdk = AutohandSDK(config, **kwargs)
        await sdk.start()
        return cls(sdk)

    @classmethod
    def from_sdk(cls, sdk: AutohandSDK) -> Agent:
        """Wrap an existing low-level SDK instance."""
        return cls(sdk)

    async def close(self) -> None:
        """Close the underlying SDK session."""
        await self._sdk.close()

    async def reset(self) -> ResetResult:
        """Reset the conversation context."""
        return await self._sdk.reset()

    async def acknowledge_permission(self, request_id: str) -> PermissionAcknowledgedResult:
        """Acknowledge receipt of a permission request before deciding it."""
        return await self._sdk.acknowledge_permission(request_id)

    async def respond_to_directory_access(
        self, request_id: str, granted: bool
    ) -> DirectoryAccessResponseResult:
        """Grant or deny a pending directory-access request."""
        return await self._sdk.respond_to_directory_access(request_id, granted)

    async def acknowledge_directory_access(
        self, request_id: str
    ) -> DirectoryAccessAcknowledgedResult:
        """Acknowledge receipt of a directory-access request."""
        return await self._sdk.acknowledge_directory_access(request_id)

    async def decide_changes(
        self,
        batch_id: str,
        action: ChangesDecisionAction,
        *,
        selected_change_ids: list[str] | None = None,
    ) -> ChangesDecisionResult:
        """Apply or reject a batch of proposed file changes."""
        return await self._sdk.decide_changes(
            batch_id,
            action,
            selected_change_ids=selected_change_ids,
        )

    async def get_history(
        self,
        *,
        page: int | None = None,
        page_size: int | None = None,
    ) -> GetHistoryResult:
        """Return paginated saved-session metadata."""
        return await self._sdk.get_history(page=page, page_size=page_size)

    async def get_session(self, session_id: str) -> GetSessionResult:
        """Return one saved session with messages and workspace metadata."""
        return await self._sdk.get_session(session_id)

    async def attach_session(self, session_id: str) -> SessionAttachResult:
        """Attach this agent to a saved session."""
        return await self._sdk.attach_session(session_id)

    async def set_yolo(self, pattern: str, *, timeout_seconds: int | None = None) -> YoloSetResult:
        """Set timed unrestricted mode through the canonical RPC."""
        return await self._sdk.set_yolo(pattern, timeout_seconds=timeout_seconds)

    async def set_yolo_compat(
        self, pattern: str, *, timeout_seconds: int | None = None
    ) -> YoloSetResult:
        """Set timed unrestricted mode through the legacy dotted RPC."""
        return await self._sdk.set_yolo_compat(pattern, timeout_seconds=timeout_seconds)

    async def set_vscode_mcp_tools(
        self,
        tools: list[VscodeMcpToolDescriptor | dict[str, Any]],
    ) -> McpSetVscodeToolsResult:
        """Replace the CLI's VS Code-hosted MCP tool descriptors."""
        return await self._sdk.set_vscode_mcp_tools(tools)

    async def respond_to_mcp_invocation(
        self,
        request_id: str,
        *,
        success: bool,
        result: str | None = None,
        error: str | None = None,
    ) -> McpInvokeResponseResult:
        """Resolve a VS Code-hosted MCP invocation."""
        return await self._sdk.respond_to_mcp_invocation(
            request_id,
            success=success,
            result=result,
            error=error,
        )

    async def create_browser_handoff(
        self,
        extension_id: str | None = None,
        install_url: str | None = None,
    ) -> BrowserHandoffCreateResult:
        """Create a browser handoff for the active session."""
        return await self._sdk.create_browser_handoff(extension_id, install_url)

    async def attach_browser_handoff(self, token: str) -> BrowserHandoffAttachResult:
        """Consume a browser handoff token and attach its session."""
        return await self._sdk.attach_browser_handoff(token)

    async def attach_latest_browser_handoff(self) -> BrowserHandoffAttachLatestResult:
        """Attach the newest pending browser handoff."""
        return await self._sdk.attach_latest_browser_handoff()

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
    ) -> AutomodeStartResult:
        """Start an autonomous execution session."""
        return await self._sdk.start_automode(
            prompt,
            max_iterations=max_iterations,
            completion_promise=completion_promise,
            use_worktree=use_worktree,
            checkpoint_interval=checkpoint_interval,
            max_runtime=max_runtime,
            max_cost=max_cost,
        )

    async def get_automode_status(self) -> AutomodeStatusResult:
        """Get the current autonomous execution status."""
        return await self._sdk.get_automode_status()

    async def pause_automode(self) -> AutomodeOperationResult:
        """Pause the active autonomous execution session."""
        return await self._sdk.pause_automode()

    async def resume_automode(self) -> AutomodeResumeResult:
        """Resume a paused autonomous execution session."""
        return await self._sdk.resume_automode()

    async def cancel_automode(self, reason: str | None = None) -> AutomodeCancelResult:
        """Cancel the active autonomous execution session."""
        return await self._sdk.cancel_automode(reason)

    async def get_automode_log(self, limit: int | None = None) -> AutomodeGetLogResult:
        """Get auto-mode iteration log entries."""
        return await self._sdk.get_automode_log(limit)

    async def command(
        self,
        command: str,
        args: str | list[str] | tuple[str, ...] | None = None,
        **kwargs: Any,
    ) -> PromptResult:
        """Run a slash command to completion."""
        return await self._sdk.command(command, args, **kwargs)

    async def deep_research(self, topic: str, **kwargs: Any) -> PromptResult:
        """Run the CLI's ``/deep-research`` command."""
        return await self._sdk.deep_research(topic, **kwargs)

    async def autoresearch(self, objective: str, **kwargs: Any) -> PromptResult:
        """Run the CLI's ``/autoresearch`` command."""
        return await self._sdk.autoresearch(objective, **kwargs)

    async def supported_commands(self) -> list[str]:
        """Return slash commands supported by the current CLI."""
        return await self._sdk.supported_commands()

    async def supports_command(self, command: str) -> bool:
        """Return whether the current CLI supports a slash command."""
        return await self._sdk.supports_command(command)

    async def get_skills_registry(
        self,
        force_refresh: bool | None = None,
    ) -> GetSkillsRegistryResult:
        """Return the community skill registry."""
        return await self._sdk.get_skills_registry(force_refresh)

    async def install_skill(
        self,
        skill_name: str,
        scope: Literal["user", "project"],
        force: bool | None = None,
    ) -> InstallSkillResult:
        """Install one community skill."""
        return await self._sdk.install_skill(skill_name, scope, force)

    async def list_mcp_servers(self) -> McpListServersResult:
        """List known MCP servers."""
        return await self._sdk.list_mcp_servers()

    async def list_mcp_tools(
        self,
        server_name: str | None = None,
    ) -> McpListToolsResult:
        """List MCP tools, optionally filtered by server."""
        return await self._sdk.list_mcp_tools(server_name)

    async def get_mcp_server_configs(self) -> McpGetServerConfigsResult:
        """Return MCP server configurations."""
        return await self._sdk.get_mcp_server_configs()

    async def set_plan_mode(self, enabled: bool) -> dict[str, Any]:
        """Enable or disable plan mode."""
        return await self._sdk.set_plan_mode(enabled)

    async def get_goal(self) -> GoalSnapshotResult:
        """Get the persistent-goal snapshot."""
        return await self._sdk.get_goal()

    async def create_goal(
        self,
        objective: str,
        *,
        token_budget: int | None = None,
        time_budget_seconds: int | None = None,
        min_tokens_before_wrap_up: int | None = None,
        min_time_seconds_before_wrap_up: int | None = None,
    ) -> GoalMutationRPCResult:
        """Create a persistent goal."""
        return await self._sdk.create_goal(
            objective,
            token_budget=token_budget,
            time_budget_seconds=time_budget_seconds,
            min_tokens_before_wrap_up=min_tokens_before_wrap_up,
            min_time_seconds_before_wrap_up=min_time_seconds_before_wrap_up,
        )

    async def update_goal(self, params: UpdateGoalParams) -> GoalMutationRPCResult:
        """Update the active persistent goal."""
        return await self._sdk.update_goal(params)

    async def clear_goal(self) -> GoalMutationRPCResult:
        """Clear the active persistent goal."""
        return await self._sdk.clear_goal()

    async def queue_goal(
        self,
        objective: str,
        *,
        token_budget: int | None = None,
        time_budget_seconds: int | None = None,
        min_tokens_before_wrap_up: int | None = None,
        min_time_seconds_before_wrap_up: int | None = None,
    ) -> GoalMutationRPCResult:
        """Queue a persistent goal."""
        return await self._sdk.queue_goal(
            objective,
            token_budget=token_budget,
            time_budget_seconds=time_budget_seconds,
            min_tokens_before_wrap_up=min_tokens_before_wrap_up,
            min_time_seconds_before_wrap_up=min_time_seconds_before_wrap_up,
        )

    async def start_queued_goal(self) -> GoalMutationRPCResult:
        """Start the next queued persistent goal."""
        return await self._sdk.start_queued_goal()

    async def list_goal_templates(self) -> GoalTemplatesResult:
        """List available persistent-goal templates."""
        return await self._sdk.list_goal_templates()
