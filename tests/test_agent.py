"""Tests for the high-level Agent facade."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autohand_sdk import Agent, AutohandSDK, UpdateGoalParams
from autohand_sdk.types import PromptResult


@pytest.mark.asyncio
async def test_create_starts_and_close_stops_sdk() -> None:
    """Agent.create owns SDK startup and close delegates shutdown."""
    with patch("autohand_sdk.agent.AutohandSDK") as sdk_class:
        sdk = MagicMock(spec=AutohandSDK)
        sdk.start = AsyncMock()
        sdk.close = AsyncMock()
        sdk_class.return_value = sdk

        agent = await Agent.create(cwd=".")
        await agent.close()

    sdk_class.assert_called_once_with(None, cwd=".")
    sdk.start.assert_awaited_once()
    sdk.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_reset_delegates_to_sdk() -> None:
    """Agent exposes conversation reset."""
    sdk = MagicMock(spec=AutohandSDK)
    sdk.reset = AsyncMock(return_value="reset")

    assert await Agent.from_sdk(sdk).reset() == "reset"
    sdk.reset.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_create_browser_handoff_delegates_to_sdk() -> None:
    """Agent exposes browser handoff creation."""
    sdk = MagicMock(spec=AutohandSDK)
    sdk.create_browser_handoff = AsyncMock(return_value="handoff")

    result = await Agent.from_sdk(sdk).create_browser_handoff("ext", "https://install.test")

    assert result == "handoff"
    sdk.create_browser_handoff.assert_awaited_once_with("ext", "https://install.test")


@pytest.mark.asyncio
async def test_attach_browser_handoff_delegates_to_sdk() -> None:
    """Agent exposes browser handoff attachment."""
    sdk = MagicMock(spec=AutohandSDK)
    sdk.attach_browser_handoff = AsyncMock(return_value="attached")

    assert await Agent.from_sdk(sdk).attach_browser_handoff("token-1") == "attached"
    sdk.attach_browser_handoff.assert_awaited_once_with("token-1")


@pytest.mark.asyncio
async def test_attach_latest_browser_handoff_delegates_to_sdk() -> None:
    """Agent exposes latest browser handoff attachment."""
    sdk = MagicMock(spec=AutohandSDK)
    sdk.attach_latest_browser_handoff = AsyncMock(return_value="latest")

    assert await Agent.from_sdk(sdk).attach_latest_browser_handoff() == "latest"
    sdk.attach_latest_browser_handoff.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_start_automode_delegates_to_sdk() -> None:
    """Agent exposes autonomous execution start."""
    sdk = MagicMock(spec=AutohandSDK)
    sdk.start_automode = AsyncMock(return_value="started")

    result = await Agent.from_sdk(sdk).start_automode(
        "Ship",
        max_iterations=10,
        use_worktree=False,
    )

    assert result == "started"
    sdk.start_automode.assert_awaited_once_with(
        "Ship",
        max_iterations=10,
        completion_promise=None,
        use_worktree=False,
        checkpoint_interval=None,
        max_runtime=None,
        max_cost=None,
    )


@pytest.mark.asyncio
async def test_get_automode_status_delegates_to_sdk() -> None:
    """Agent exposes autonomous execution status."""
    sdk = MagicMock(spec=AutohandSDK)
    sdk.get_automode_status = AsyncMock(return_value="status")

    assert await Agent.from_sdk(sdk).get_automode_status() == "status"
    sdk.get_automode_status.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_command_and_capability_helpers_delegate() -> None:
    """Command execution and capability checks delegate to the SDK."""
    sdk = MagicMock(spec=AutohandSDK)
    sdk.command = AsyncMock(return_value=PromptResult(content="command"))
    sdk.deep_research = AsyncMock(return_value=PromptResult(content="deep"))
    sdk.autoresearch = AsyncMock(return_value=PromptResult(content="auto"))
    sdk.supported_commands = AsyncMock(return_value=["/deep-research", "/autoresearch"])
    sdk.supports_command = AsyncMock(return_value=True)
    agent = Agent.from_sdk(sdk)

    command = await agent.command("review", ["src", "tests"])
    deep = await agent.deep_research("architecture")
    auto = await agent.autoresearch("latency")
    commands = await agent.supported_commands()
    supported = await agent.supports_command("autoresearch")

    assert command.content == "command"
    assert deep.content == "deep"
    assert auto.content == "auto"
    assert commands == ["/deep-research", "/autoresearch"]
    assert supported is True
    sdk.command.assert_awaited_once_with("review", ["src", "tests"])
    sdk.deep_research.assert_awaited_once_with("architecture")
    sdk.autoresearch.assert_awaited_once_with("latency")


@pytest.mark.asyncio
async def test_all_persistent_goal_helpers_delegate() -> None:
    """All seven persistent-goal operations are exposed by Agent."""
    sdk = MagicMock(spec=AutohandSDK)
    sdk.get_goal = AsyncMock(return_value="snapshot")
    sdk.create_goal = AsyncMock(return_value="created")
    sdk.update_goal = AsyncMock(return_value="updated")
    sdk.clear_goal = AsyncMock(return_value="cleared")
    sdk.queue_goal = AsyncMock(return_value="queued")
    sdk.start_queued_goal = AsyncMock(return_value="started")
    sdk.list_goal_templates = AsyncMock(return_value=[])
    agent = Agent.from_sdk(sdk)
    update = UpdateGoalParams(status="paused")

    assert await agent.get_goal() == "snapshot"
    assert await agent.create_goal("ship", token_budget=1000) == "created"
    assert await agent.update_goal(update) == "updated"
    assert await agent.clear_goal() == "cleared"
    assert await agent.queue_goal("document", time_budget_seconds=60) == "queued"
    assert await agent.start_queued_goal() == "started"
    assert await agent.list_goal_templates() == []
    sdk.create_goal.assert_awaited_once_with(
        "ship",
        token_budget=1000,
        time_budget_seconds=None,
        min_tokens_before_wrap_up=None,
        min_time_seconds_before_wrap_up=None,
    )
    sdk.update_goal.assert_awaited_once_with(update)
    sdk.queue_goal.assert_awaited_once_with(
        "document",
        token_budget=None,
        time_budget_seconds=60,
        min_tokens_before_wrap_up=None,
        min_time_seconds_before_wrap_up=None,
    )
