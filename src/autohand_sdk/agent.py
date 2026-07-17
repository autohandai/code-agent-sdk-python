"""High-level agent facade for command runs and persistent goals."""
from __future__ import annotations

from typing import Any

from autohand_sdk.sdk import AutohandSDK
from autohand_sdk.types import (
    GoalMutationRPCResult,
    GoalSnapshotResult,
    GoalTemplatesResult,
    PromptResult,
    SDKConfig,
    UpdateGoalParams,
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
