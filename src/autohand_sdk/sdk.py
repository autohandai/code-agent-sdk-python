"""Main SDK class for the Autohand Python SDK."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Any, Literal, cast

from autohand_sdk.errors import TransportError
from autohand_sdk.rpc_client import RPCClient
from autohand_sdk.types import (
    AbortParams,
    AbortResult,
    AutomodeStartParams,
    AutomodeStartResult,
    AutoresearchCompareParams,
    AutoresearchCompareResult,
    AutoresearchConstraint,
    AutoresearchHistoryResult,
    AutoresearchParetoResult,
    AutoresearchPinParams,
    AutoresearchPinResult,
    AutoresearchPruneParams,
    AutoresearchPruneResult,
    AutoresearchReplayParams,
    AutoresearchReplayResult,
    AutoresearchRescoreParams,
    AutoresearchRescoreResult,
    AutoresearchRetentionOptions,
    AutoresearchSamplingOptions,
    AutoresearchSecondaryObjective,
    AutoresearchStartParams,
    AutoresearchStartResult,
    AutoresearchStatusResult,
    AutoresearchStopResult,
    AutoresearchSubagentOptions,
    BrowserHandoffAttachLatestResult,
    BrowserHandoffAttachParams,
    BrowserHandoffAttachResult,
    BrowserHandoffCreateParams,
    BrowserHandoffCreateResult,
    CreateGoalParams,
    FeatureFlagSettings,
    GetMessagesParams,
    GetMessagesResult,
    GetSkillsRegistryResult,
    GetStateParams,
    GetStateResult,
    GoalFeatureDisabledResult,
    GoalMutationResult,
    GoalMutationRPCResult,
    GoalSnapshot,
    GoalSnapshotResult,
    GoalTemplateMetadata,
    GoalTemplatesResult,
    InstallSkillResult,
    McpGetServerConfigsResult,
    McpListServersResult,
    McpListToolsResult,
    PermissionResponseParams,
    PromptParams,
    PromptResult,
    ResetResult,
    SDKConfig,
    SDKEvent,
    SkillReference,
    UpdateGoalParams,
)

logger = logging.getLogger(__name__)


class AutohandSDK:
    """Main SDK class for interacting with the Autohand CLI."""

    def __init__(self, config: SDKConfig | None = None, **kwargs: Any) -> None:
        """Initialize the SDK.

        Args:
            config: SDK configuration.
            **kwargs: Additional configuration options (merged with config).
        """
        if config is None:
            config = SDKConfig.model_validate({})

        # Merge kwargs into config
        if kwargs:
            config_data = config.model_dump(by_alias=True)
            config_data.update(kwargs)
            config = SDKConfig.model_validate(config_data)

        self._config = config
        self._client: RPCClient | None = None
        self._started = False
        self._starting = False
        self._lifecycle_lock = asyncio.Lock()

        # Initialize skills from config
        self._skills: list[SkillReference] = []
        if config.skill_refs:
            self._skills = config.skill_refs.copy()
        elif config.skills and config.skills.skills:
            self._skills = config.skills.skills.copy()

        # Initialize client
        self._client = RPCClient(
            self._config,
            termination_callback=self._handle_client_termination,
        )

    @property
    def config(self) -> SDKConfig:
        """Get the SDK configuration."""
        return self._config

    @property
    def skills(self) -> list[SkillReference]:
        """Get the current skills configuration."""
        return self._skills.copy()

    @skills.setter
    def skills(self, skills: list[SkillReference]) -> None:
        """Set the skills configuration.

        Must be called before start() for changes to take effect.

        Args:
            skills: List of skill references.
        """
        if (
            self._starting
            or self._started
            or (self._client is not None and self._client.is_running())
        ):
            raise RuntimeError(
                "skills must be configured before start(); stop the SDK before changing skills"
            )

        self._skills = skills.copy()
        # Update config for consistency
        self._config = self._config.model_copy(update={"skill_refs": self._skills})
        # Recreate client with new config
        self._client = RPCClient(
            self._config,
            termination_callback=self._handle_client_termination,
        )

    async def start(self) -> None:
        """Start the SDK.

        Initializes the RPC client and connects to the CLI subprocess.
        """
        async with self._lifecycle_lock:
            await self._start_locked()

    async def _start_locked(self) -> None:
        """Start once while the SDK lifecycle lock is held."""
        if self._started and self._client is not None and self._client.is_running():
            return
        self._starting = True
        client = self._client
        try:
            self._started = False

            if client is None:
                raise RuntimeError("RPC client not initialized")

            # Rebuild client if skills changed
            if (self._config.skill_refs or []) != self._skills:
                if client.is_running():
                    raise RuntimeError(
                        "cannot rebuild the RPC client while its CLI transport is running"
                    )
                self._config = self._config.model_copy(update={"skill_refs": self._skills})
                client = RPCClient(
                    self._config,
                    termination_callback=self._handle_client_termination,
                )
                self._client = client

            await client.start()
            if self._config.plan_mode is not None:
                await client.set_plan_mode(self._config.plan_mode)
            if self._config.features is not None:
                await client.apply_flag_settings(
                    {
                        "features": self._config.features.model_dump(
                            by_alias=True,
                            exclude_none=True,
                        )
                    }
                )
            if not client._started or not client.is_running():
                raise TransportError("CLI transport stopped during post-start configuration")
            self._started = True
        except BaseException:
            self._started = False
            if client is not None:
                with suppress(Exception):
                    await client.stop()
            raise
        finally:
            self._starting = False

    async def stop(self) -> None:
        """Stop the SDK.

        Terminates the CLI subprocess and cleans up resources.
        """
        async with self._lifecycle_lock:
            if self._client:
                await self._client.stop()
            self._started = False

    async def close(self) -> None:
        """Alias for stop()."""
        await self.stop()

    async def __aenter__(self) -> AutohandSDK:
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.stop()

    def _handle_client_termination(self, _error: BaseException) -> None:
        """Synchronize public SDK state with an unexpected CLI termination."""
        self._started = False

    def stream_prompt(self, message: str, **kwargs: Any) -> AsyncIterator[SDKEvent]:
        """Stream a prompt to the agent.

        Args:
            message: The message to send.
            **kwargs: Additional prompt parameters.

        Yields:
            Events from the agent.
        """
        params = PromptParams(message=message, **kwargs)
        return self._stream_prompt(params)

    async def _stream_prompt(self, params: PromptParams) -> AsyncIterator[SDKEvent]:
        """Internal implementation of prompt streaming."""
        if not self._client:
            raise RuntimeError("SDK not started")

        async for event in self._client.prompt(params.model_dump(by_alias=True, exclude_none=True)):
            yield event

    async def abort(self, reason: str | None = None) -> AbortResult:
        """Abort the current operation.

        Args:
            reason: Optional reason for aborting.

        Returns:
            Result of the abort operation.
        """
        if not self._client:
            raise RuntimeError("SDK not started")

        params = AbortParams(reason=reason)
        result = await self._client.abort(params.model_dump(by_alias=True, exclude_none=True))
        return AbortResult(**result)

    async def reset(self) -> ResetResult:
        """Reset the conversation context and return the new session ID."""
        if not self._client:
            raise RuntimeError("SDK not started")

        result = await self._client.reset()
        return ResetResult.model_validate(result)

    async def create_browser_handoff(
        self,
        extension_id: str | None = None,
        install_url: str | None = None,
    ) -> BrowserHandoffCreateResult:
        """Create a browser handoff for the active session."""
        if not self._client:
            raise RuntimeError("SDK not started")

        params = BrowserHandoffCreateParams(
            extension_id=extension_id,
            install_url=install_url,
        )
        result = await self._client.create_browser_handoff(
            extension_id=params.extension_id,
            install_url=params.install_url,
        )
        return BrowserHandoffCreateResult.model_validate(result)

    async def attach_browser_handoff(self, token: str) -> BrowserHandoffAttachResult:
        """Consume a browser handoff token and attach its session."""
        if not self._client:
            raise RuntimeError("SDK not started")

        params = BrowserHandoffAttachParams(token=token)
        result = await self._client.attach_browser_handoff(params.token)
        return BrowserHandoffAttachResult.model_validate(result)

    async def attach_latest_browser_handoff(self) -> BrowserHandoffAttachLatestResult:
        """Attach the newest pending browser handoff."""
        if not self._client:
            raise RuntimeError("SDK not started")

        result = await self._client.attach_latest_browser_handoff()
        return BrowserHandoffAttachResult.model_validate(result)

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
        if not self._client:
            raise RuntimeError("SDK not started")

        params = AutomodeStartParams(
            prompt=prompt,
            max_iterations=max_iterations,
            completion_promise=completion_promise,
            use_worktree=use_worktree,
            checkpoint_interval=checkpoint_interval,
            max_runtime=max_runtime,
            max_cost=max_cost,
        )
        result = await self._client.start_automode(
            params.prompt,
            max_iterations=params.max_iterations,
            completion_promise=params.completion_promise,
            use_worktree=params.use_worktree,
            checkpoint_interval=params.checkpoint_interval,
            max_runtime=params.max_runtime,
            max_cost=params.max_cost,
        )
        return AutomodeStartResult.model_validate(result)

    async def respond_to_permission(
        self,
        request_id: str,
        decision: str | None = None,
        allowed: bool | None = None,
        alternative: str | None = None,
        remember: bool | None = None,
    ) -> dict[str, Any]:
        """Respond to a permission request.

        Args:
            request_id: The permission request ID.
            decision: The decision ('allow', 'deny', or custom).
            allowed: Whether the request is allowed.
            alternative: Alternative command if denying.
            remember: Whether to remember this decision.

        Returns:
            Result from the permission response.
        """
        if not self._client:
            raise RuntimeError("SDK not started")

        params = PermissionResponseParams(
            requestId=request_id,
            decision=decision,
            allowed=allowed,
            alternative=alternative,
            remember=remember,
        )
        return await self._client.respond_to_permission(
            params.model_dump(by_alias=True, exclude_none=True)
        )

    async def get_state(self, include_context: bool | None = None) -> GetStateResult:
        """Get the current agent state.

        Args:
            include_context: Whether to include context information.

        Returns:
            Current agent state.
        """
        if not self._client:
            raise RuntimeError("SDK not started")

        params = GetStateParams(includeContext=include_context)
        result = await self._client.get_state(params.model_dump(by_alias=True, exclude_none=True))
        return GetStateResult(**result)

    async def get_messages(
        self, limit: int | None = None, before: str | None = None
    ) -> GetMessagesResult:
        """Get messages from the agent.

        Args:
            limit: Maximum number of messages to return.
            before: Return messages before this message ID.

        Returns:
            Messages from the agent.
        """
        if not self._client:
            raise RuntimeError("SDK not started")

        params = GetMessagesParams(limit=limit, before=before)
        result = await self._client.get_messages(
            params.model_dump(by_alias=True, exclude_none=True)
        )
        return GetMessagesResult(**result)

    async def get_models(self) -> list[dict[str, Any]]:
        """Get available models.

        Returns:
            List of available models.
        """
        if not self._client:
            raise RuntimeError("SDK not started")

        result = await self._client.get_models()
        return cast(list[dict[str, Any]], result.get("models", []))

    async def get_agents(self) -> list[dict[str, Any]]:
        """Get available agents.

        Returns:
            List of available agents.
        """
        if not self._client:
            raise RuntimeError("SDK not started")

        result = await self._client.get_agents()
        agents = result.get("agents", result.get("commands", []))
        return cast(list[dict[str, Any]], agents)

    async def get_skills_registry(
        self,
        force_refresh: bool | None = None,
    ) -> GetSkillsRegistryResult:
        """Return the typed community skill registry."""
        if not self._client:
            raise RuntimeError("SDK not started")
        return GetSkillsRegistryResult.model_validate(
            await self._client.get_skills_registry(force_refresh)
        )

    async def install_skill(
        self,
        skill_name: str,
        scope: Literal["user", "project"],
        force: bool | None = None,
    ) -> InstallSkillResult:
        """Install one community skill in user or project scope."""
        if not self._client:
            raise RuntimeError("SDK not started")
        return InstallSkillResult.model_validate(
            await self._client.install_skill(skill_name, scope, force)
        )

    async def list_mcp_servers(self) -> McpListServersResult:
        """List known MCP servers and their connection status."""
        if not self._client:
            raise RuntimeError("SDK not started")
        return McpListServersResult.model_validate(await self._client.list_mcp_servers())

    async def list_mcp_tools(
        self,
        server_name: str | None = None,
    ) -> McpListToolsResult:
        """List MCP tools, optionally filtering by server name."""
        if not self._client:
            raise RuntimeError("SDK not started")
        return McpListToolsResult.model_validate(await self._client.list_mcp_tools(server_name))

    async def get_mcp_server_configs(self) -> McpGetServerConfigsResult:
        """Return the CLI's typed MCP server configurations."""
        if not self._client:
            raise RuntimeError("SDK not started")
        return McpGetServerConfigsResult.model_validate(await self._client.get_mcp_server_configs())

    async def supported_commands(self) -> list[str]:
        """Return CLI slash commands normalized with a leading slash."""
        if not self._client:
            raise RuntimeError("SDK not started")

        result = await self._client.get_agents()
        raw_commands = result.get("commands", [])
        if not isinstance(raw_commands, list):
            return []
        return [
            command if command.startswith("/") else f"/{command}"
            for command in raw_commands
            if isinstance(command, str)
        ]

    async def supports_command(self, command: str) -> bool:
        """Return whether the current CLI exposes a slash command."""
        normalized = command if command.startswith("/") else f"/{command}"
        return normalized in await self.supported_commands()

    def stream_command(
        self,
        command: str,
        args: str | list[str] | tuple[str, ...] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[SDKEvent]:
        """Stream a CLI slash command through the normal prompt channel."""
        return self.stream_prompt(self._format_slash_command(command, args), **kwargs)

    async def command(
        self,
        command: str,
        args: str | list[str] | tuple[str, ...] | None = None,
        **kwargs: Any,
    ) -> PromptResult:
        """Run a CLI slash command to completion."""
        content = ""
        message_id: str | None = None
        async for event in self.stream_command(command, args, **kwargs):
            if event.get("type") == "message_update":
                content += str(event.get("delta", ""))
            elif event.get("type") == "message_end":
                content = str(event.get("content", content))
                raw_message_id = event.get("message_id", event.get("messageId"))
                message_id = str(raw_message_id) if raw_message_id is not None else None
        return PromptResult(message_id=message_id, content=content)

    async def deep_research(self, topic: str, **kwargs: Any) -> PromptResult:
        """Run the CLI's ``/deep-research`` command."""
        return await self.command("/deep-research", topic, **kwargs)

    async def autoresearch(self, objective: str, **kwargs: Any) -> PromptResult:
        """Run the CLI's ``/autoresearch`` slash command."""
        return await self.command("/autoresearch", objective, **kwargs)

    async def set_model(self, model: str) -> dict[str, Any]:
        """Set the model.

        Args:
            model: The model ID to use.

        Returns:
            Result of the set model operation.
        """
        if not self._client:
            raise RuntimeError("SDK not started")

        # Update config
        self._config = self._config.model_copy(update={"model": model})

        return await self._client.set_model(model)

    async def set_plan_mode(self, enabled: bool) -> dict[str, Any]:
        """Enable or disable plan mode for the live CLI session."""
        if not self._client:
            raise RuntimeError("SDK not started")
        result = await self._client.set_plan_mode(enabled)
        self._config = self._config.model_copy(update={"plan_mode": enabled})
        return result

    async def set_agent(self, agent: str) -> dict[str, Any]:
        """Set the agent.

        Args:
            agent: The agent ID to use.

        Returns:
            Result of the set agent operation.
        """
        if not self._client:
            raise RuntimeError("SDK not started")

        return await self._client.set_agent(agent)

    async def set_temperature(self, temperature: float) -> dict[str, Any]:
        """Set the temperature.

        Args:
            temperature: The temperature value (0.0 to 2.0).

        Returns:
            Result of the set temperature operation.
        """
        if not self._client:
            raise RuntimeError("SDK not started")

        # Update config
        self._config = self._config.model_copy(update={"temperature": temperature})

        return await self._client.set_temperature(temperature)

    async def apply_flag_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Merge public runtime settings into the CLI flag-settings layer."""
        if not self._client:
            raise RuntimeError("SDK not started")
        return await self._client.apply_flag_settings(settings)

    async def apply_feature_settings(
        self,
        settings: FeatureFlagSettings,
    ) -> dict[str, Any]:
        """Apply current CLI feature settings at runtime."""
        result = await self.apply_flag_settings(
            {"features": settings.model_dump(by_alias=True, exclude_none=True)}
        )
        self._config = self._config.model_copy(update={"features": settings})
        return result

    async def get_account_info(self) -> dict[str, Any]:
        """Get account information.

        Returns:
            Account information.
        """
        if not self._client:
            raise RuntimeError("SDK not started")

        return await self._client.get_account_info()

    async def save_session(self) -> dict[str, Any]:
        """Save the current session.

        Returns:
            Result of the save session operation.
        """
        if not self._client:
            raise RuntimeError("SDK not started")

        return await self._client.save_session()

    async def get_goal(self) -> GoalSnapshotResult:
        """Get the active persistent goal, queue, and completed goals."""
        if not self._client:
            raise RuntimeError("SDK not started")
        result = await self._client.get_goal()
        if result.get("ok") is False:
            return GoalFeatureDisabledResult.model_validate(result)
        return GoalSnapshot.model_validate(result)

    async def create_goal(
        self,
        objective: str,
        *,
        token_budget: int | None = None,
        time_budget_seconds: int | None = None,
        min_tokens_before_wrap_up: int | None = None,
        min_time_seconds_before_wrap_up: int | None = None,
    ) -> GoalMutationRPCResult:
        """Create a persistent goal with optional token and time budgets."""
        params = CreateGoalParams(
            objective=objective,
            token_budget=token_budget,
            time_budget_seconds=time_budget_seconds,
            min_tokens_before_wrap_up=min_tokens_before_wrap_up,
            min_time_seconds_before_wrap_up=min_time_seconds_before_wrap_up,
        )
        return await self._goal_mutation(
            "create_goal", params.model_dump(by_alias=True, exclude_none=True)
        )

    async def update_goal(self, params: UpdateGoalParams) -> GoalMutationRPCResult:
        """Update fields on the active persistent goal."""
        return await self._goal_mutation(
            "update_goal",
            params.model_dump(by_alias=True, exclude_unset=True),
        )

    async def clear_goal(self) -> GoalMutationRPCResult:
        """Clear the active persistent goal."""
        return await self._goal_mutation("clear_goal")

    async def queue_goal(
        self,
        objective: str,
        *,
        token_budget: int | None = None,
        time_budget_seconds: int | None = None,
        min_tokens_before_wrap_up: int | None = None,
        min_time_seconds_before_wrap_up: int | None = None,
    ) -> GoalMutationRPCResult:
        """Queue a persistent goal to run after the active goal."""
        params = CreateGoalParams(
            objective=objective,
            token_budget=token_budget,
            time_budget_seconds=time_budget_seconds,
            min_tokens_before_wrap_up=min_tokens_before_wrap_up,
            min_time_seconds_before_wrap_up=min_time_seconds_before_wrap_up,
        )
        return await self._goal_mutation(
            "queue_goal", params.model_dump(by_alias=True, exclude_none=True)
        )

    async def start_queued_goal(self) -> GoalMutationRPCResult:
        """Start the next queued persistent goal."""
        return await self._goal_mutation("start_queued_goal")

    async def list_goal_templates(self) -> GoalTemplatesResult:
        """List available persistent-goal templates."""
        if not self._client:
            raise RuntimeError("SDK not started")
        result = await self._client.list_goal_templates()
        if isinstance(result, dict):
            return GoalFeatureDisabledResult.model_validate(result)
        return [GoalTemplateMetadata.model_validate(template) for template in result]

    async def _goal_mutation(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> GoalMutationRPCResult:
        """Call and validate a persistent-goal mutation RPC."""
        if not self._client:
            raise RuntimeError("SDK not started")
        client_method = getattr(self._client, method)
        result = await client_method(params) if params is not None else await client_method()
        if result.get("ok") is False:
            return GoalFeatureDisabledResult.model_validate(result)
        return GoalMutationResult.model_validate(result)

    @staticmethod
    def _format_slash_command(
        command: str,
        args: str | list[str] | tuple[str, ...] | None = None,
    ) -> str:
        """Normalize a slash command and optional arguments."""
        normalized = command.strip()
        if not normalized:
            raise ValueError("command must not be empty")
        if not normalized.startswith("/"):
            normalized = f"/{normalized}"
        if args is None:
            return normalized
        arg_text = " ".join(args) if isinstance(args, (list, tuple)) else args
        arg_text = arg_text.strip()
        return f"{normalized} {arg_text}" if arg_text else normalized

    async def start_autoresearch(  # noqa: PLR0913 - public RPC options remain explicit and typed
        self,
        objective: str,
        *,
        max_iterations: int | None = None,
        timeout_ms: int | None = None,
        metric_name: str | None = None,
        metric_unit: str | None = None,
        direction: Literal["lower", "higher"] | None = None,
        measure_command: str | None = None,
        measure_script: str | None = None,
        checks_command: str | None = None,
        checks_script: str | None = None,
        files_in_scope: list[str] | None = None,
        subagents: AutoresearchSubagentOptions | None = None,
        secondary_objectives: list[AutoresearchSecondaryObjective] | None = None,
        constraints: list[AutoresearchConstraint] | None = None,
        sampling: AutoresearchSamplingOptions | None = None,
        retention: AutoresearchRetentionOptions | None = None,
        environment_allowlist: list[str] | None = None,
    ) -> AutoresearchStartResult:
        """Initialize or resume a replayable autoresearch session."""
        if not self._client:
            raise RuntimeError("SDK not started")

        params = AutoresearchStartParams(
            objective=objective,
            max_iterations=max_iterations,
            timeout_ms=timeout_ms,
            metric_name=metric_name,
            metric_unit=metric_unit,
            direction=direction,
            measure_command=measure_command,
            measure_script=measure_script,
            checks_command=checks_command,
            checks_script=checks_script,
            files_in_scope=files_in_scope,
            subagents=subagents,
            secondary_objectives=secondary_objectives,
            constraints=constraints,
            sampling=sampling,
            retention=retention,
            environment_allowlist=environment_allowlist,
        )
        result = await self._client.start_autoresearch(
            params.model_dump(by_alias=True, exclude_none=True)
        )
        return AutoresearchStartResult.model_validate(result)

    async def get_autoresearch_status(self) -> AutoresearchStatusResult:
        """Read active autoresearch state, progress, attempts, and Pareto IDs."""
        if not self._client:
            raise RuntimeError("SDK not started")
        return AutoresearchStatusResult.model_validate(await self._client.get_autoresearch_status())

    async def stop_autoresearch(self) -> AutoresearchStopResult:
        """Pause autoresearch without deleting its persisted state."""
        if not self._client:
            raise RuntimeError("SDK not started")
        return AutoresearchStopResult.model_validate(await self._client.stop_autoresearch())

    async def get_autoresearch_history(self) -> AutoresearchHistoryResult:
        """List immutable attempts and their replay/materialization state."""
        if not self._client:
            raise RuntimeError("SDK not started")
        return AutoresearchHistoryResult.model_validate(
            await self._client.get_autoresearch_history()
        )

    async def replay_autoresearch(
        self,
        attempt_id: str,
        evaluator: Literal["original", "current"] | None = None,
    ) -> AutoresearchReplayResult:
        """Re-evaluate an attempt in an isolated worktree."""
        if not self._client:
            raise RuntimeError("SDK not started")
        params = AutoresearchReplayParams(attempt_id=attempt_id, evaluator=evaluator)
        result = await self._client.replay_autoresearch(
            params.model_dump(by_alias=True, exclude_none=True)
        )
        return AutoresearchReplayResult.model_validate(result)

    async def rescore_autoresearch(
        self,
        *,
        attempt_id: str | None = None,
        all: bool | None = None,
    ) -> AutoresearchRescoreResult:
        """Append decisions from stored measurements and current policy."""
        if not self._client:
            raise RuntimeError("SDK not started")
        params = AutoresearchRescoreParams(attempt_id=attempt_id, all=all)
        result = await self._client.rescore_autoresearch(
            params.model_dump(by_alias=True, exclude_none=True)
        )
        return AutoresearchRescoreResult.model_validate(result)

    async def compare_autoresearch(
        self,
        left_attempt_id: str,
        right_attempt_id: str,
    ) -> AutoresearchCompareResult:
        """Compare samples, aggregates, checks, and decisions."""
        if not self._client:
            raise RuntimeError("SDK not started")
        params = AutoresearchCompareParams(
            left_attempt_id=left_attempt_id,
            right_attempt_id=right_attempt_id,
        )
        result = await self._client.compare_autoresearch(
            params.model_dump(by_alias=True, exclude_none=True)
        )
        return AutoresearchCompareResult.model_validate(result)

    async def get_autoresearch_pareto(self) -> AutoresearchParetoResult:
        """List constraint-passing non-dominated attempts."""
        if not self._client:
            raise RuntimeError("SDK not started")
        return AutoresearchParetoResult.model_validate(await self._client.get_autoresearch_pareto())

    async def pin_autoresearch(self, attempt_id: str, pinned: bool) -> AutoresearchPinResult:
        """Protect or release an attempt's artifacts from pruning."""
        if not self._client:
            raise RuntimeError("SDK not started")
        params = AutoresearchPinParams(attempt_id=attempt_id, pinned=pinned)
        result = await self._client.pin_autoresearch(
            params.model_dump(by_alias=True, exclude_none=True)
        )
        return AutoresearchPinResult.model_validate(result)

    async def prune_autoresearch(
        self,
        *,
        dry_run: bool | None = None,
        yes: bool | None = None,
    ) -> AutoresearchPruneResult:
        """Preview or explicitly apply autoresearch artifact pruning."""
        if not self._client:
            raise RuntimeError("SDK not started")
        params = AutoresearchPruneParams(dry_run=dry_run, yes=yes)
        result = await self._client.prune_autoresearch(
            params.model_dump(by_alias=True, exclude_none=True)
        )
        return AutoresearchPruneResult.model_validate(result)

    def is_running(self) -> bool:
        """Check if the SDK is running.

        Returns:
            True if the SDK is running, False otherwise.
        """
        return self._started and self._client is not None and self._client.is_running()
