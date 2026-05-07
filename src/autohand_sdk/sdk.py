"""Main SDK class for the Autohand Python SDK."""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any, cast

from autohand_sdk.rpc_client import RPCClient
from autohand_sdk.types import (
    AbortParams,
    AbortResult,
    GetMessagesParams,
    GetMessagesResult,
    GetStateParams,
    GetStateResult,
    PermissionResponseParams,
    PromptParams,
    SDKConfig,
    SDKEvent,
    SkillReference,
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

        # Initialize skills from config
        self._skills: list[SkillReference] = []
        if config.skill_refs:
            self._skills = config.skill_refs.copy()
        elif config.skills and config.skills.skills:
            self._skills = config.skills.skills.copy()

        # Initialize client
        self._client = RPCClient(self._config)

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
        self._skills = skills.copy()
        # Update config for consistency
        self._config = self._config.model_copy(update={"skill_refs": self._skills})
        # Recreate client with new config
        self._client = RPCClient(self._config)

    async def start(self) -> None:
        """Start the SDK.

        Initializes the RPC client and connects to the CLI subprocess.
        """
        if self._started:
            return

        if not self._client:
            raise RuntimeError("RPC client not initialized")

        # Rebuild client if skills changed
        if self._config.skill_refs != self._skills:
            self._config = self._config.model_copy(update={"skill_refs": self._skills})
            self._client = RPCClient(self._config)

        await self._client.start()
        self._started = True

    async def stop(self) -> None:
        """Stop the SDK.

        Terminates the CLI subprocess and cleans up resources.
        """
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

    async def get_state(
        self, include_context: bool | None = None
    ) -> GetStateResult:
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

    def is_running(self) -> bool:
        """Check if the SDK is running.

        Returns:
            True if the SDK is running, False otherwise.
        """
        return self._started and self._client is not None and self._client.is_running()
