"""Tests for the main SDK class."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autohand_sdk import AutohandSDK
from autohand_sdk.types import SDKConfig


@pytest.fixture(autouse=True)
def mock_cli_binary():
    """Mock CLI binary detection for all tests."""
    with patch("autohand_sdk.transport.Transport._detect_cli_binary", return_value="/mock/autohand"):
        yield


class TestSDKInitialization:
    """Tests for SDK initialization."""

    def test_default_init(self) -> None:
        sdk = AutohandSDK()
        assert sdk.config.model is None
        assert sdk._started is False
        assert sdk._skills == []

    def test_init_with_config(self) -> None:
        config = SDKConfig(model="fantail2", cwd="/test")
        sdk = AutohandSDK(config)
        assert sdk.config.model == "fantail2"
        assert sdk.config.cwd == "/test"

    def test_init_with_kwargs(self) -> None:
        sdk = AutohandSDK(model="fantail2", debug=True)
        assert sdk.config.model == "fantail2"
        assert sdk.config.debug is True

    def test_init_merges_kwargs(self) -> None:
        config = SDKConfig(model="fantail2")
        sdk = AutohandSDK(config, cwd="/merged")
        assert sdk.config.model == "fantail2"
        assert sdk.config.cwd == "/merged"

    def test_init_with_skills(self) -> None:
        sdk = AutohandSDK(model="fantail2", skill_refs=["typescript", "react"])
        assert sdk.skills == ["typescript", "react"]

    def test_init_with_nested_skills(self) -> None:
        from autohand_sdk.types import SkillSettings
        config = SDKConfig()
        config.skills = SkillSettings(skills=["typescript", "react"], auto_skill=True)
        sdk = AutohandSDK(config)
        assert "typescript" in sdk.skills
        assert "react" in sdk.skills


class TestSDKSkills:
    """Tests for SDK skills management."""

    def test_get_skills(self) -> None:
        sdk = AutohandSDK(skill_refs=["typescript", "react"])
        assert sdk.skills == ["typescript", "react"]

    def test_set_skills(self) -> None:
        sdk = AutohandSDK()
        sdk.skills = ["typescript", "react"]
        assert sdk.skills == ["typescript", "react"]

    def test_set_skills_updates_config(self) -> None:
        sdk = AutohandSDK()
        sdk.skills = ["typescript"]
        assert sdk._config.skill_refs == ["typescript"]

    def test_skills_returns_copy(self) -> None:
        sdk = AutohandSDK(skill_refs=["typescript"])
        skills = sdk.skills
        skills.append("react")  # Modifying returned list
        assert sdk.skills == ["typescript"]  # Original unchanged


class TestSDKLifecycle:
    """Tests for SDK lifecycle."""

    @pytest.mark.asyncio
    async def test_start(self) -> None:
        sdk = AutohandSDK()
        # Mock the entire client to avoid subprocess creation
        with patch("autohand_sdk.sdk.RPCClient") as MockClient:
            mock_instance = AsyncMock()
            MockClient.return_value = mock_instance
            # Recreate sdk with mocked client
            sdk = AutohandSDK()
            await sdk.start()
            mock_instance.start.assert_called_once()
            assert sdk._started

    @pytest.mark.asyncio
    async def test_start_already_started(self) -> None:
        sdk = AutohandSDK()
        sdk._started = True
        with patch.object(sdk._client, "start", new_callable=AsyncMock) as mock_start:
            await sdk.start()
            mock_start.assert_not_called()

    @pytest.mark.asyncio
    async def test_start_rebuilds_client_if_skills_changed(self) -> None:
        with patch("autohand_sdk.sdk.RPCClient") as MockClient:
            mock_instance = AsyncMock()
            MockClient.return_value = mock_instance
            sdk = AutohandSDK()
            sdk.skills = ["typescript"]  # Set after init
            # After setting skills, client should be recreated
            assert sdk._config.skill_refs == sdk._skills

    @pytest.mark.asyncio
    async def test_stop(self) -> None:
        sdk = AutohandSDK()
        with patch.object(sdk._client, "stop", new_callable=AsyncMock) as mock_stop:
            await sdk.stop()
            mock_stop.assert_called_once()
            assert not sdk._started

    @pytest.mark.asyncio
    async def test_close_alias(self) -> None:
        sdk = AutohandSDK()
        with patch.object(sdk._client, "stop", new_callable=AsyncMock) as mock_stop:
            await sdk.close()
            mock_stop.assert_called_once()


class TestSDKContextManager:
    """Tests for SDK async context manager."""

    @pytest.mark.asyncio
    async def test_context_manager(self) -> None:
        with patch.object(AutohandSDK, "start", new_callable=AsyncMock) as mock_start, \
             patch.object(AutohandSDK, "stop", new_callable=AsyncMock) as mock_stop:
            async with AutohandSDK():
                mock_start.assert_called_once()
            mock_stop.assert_called_once()


class TestSDKPrompt:
    """Tests for SDK prompt methods."""

    @pytest.mark.asyncio
    async def test_stream_prompt_not_started(self) -> None:
        sdk = AutohandSDK()
        sdk._client = None
        with pytest.raises(RuntimeError, match="SDK not started"):
            async for _ in sdk.stream_prompt("Hello"):
                pass

    @pytest.mark.asyncio
    async def test_stream_prompt(self) -> None:
        sdk = AutohandSDK()
        sdk._started = True

        mock_events = [
            {"type": "agent_start", "session_id": "123"},
            {"type": "message_end", "content": "Hello!"},
            {"type": "agent_end", "session_id": "123"},
        ]

        async def mock_prompt(*args, **kwargs):
            for event in mock_events:
                yield event

        with patch.object(sdk._client, "prompt", side_effect=mock_prompt):
            events = []
            async for event in sdk.stream_prompt("Hello"):
                events.append(event)
            assert len(events) == 3


class TestSDKMethods:
    """Tests for SDK helper methods."""

    @pytest.mark.asyncio
    async def test_abort_not_started(self) -> None:
        sdk = AutohandSDK()
        sdk._client = None
        with pytest.raises(RuntimeError, match="SDK not started"):
            await sdk.abort()

    @pytest.mark.asyncio
    async def test_abort(self) -> None:
        sdk = AutohandSDK()
        sdk._started = True
        with patch.object(sdk._client, "abort", new_callable=AsyncMock, return_value={"success": True, "message": None}):
            result = await sdk.abort("User cancelled")
            assert result.success is True

    @pytest.mark.asyncio
    async def test_get_state_not_started(self) -> None:
        sdk = AutohandSDK()
        sdk._client = None
        with pytest.raises(RuntimeError, match="SDK not started"):
            await sdk.get_state()

    @pytest.mark.asyncio
    async def test_get_state(self) -> None:
        sdk = AutohandSDK()
        sdk._started = True
        with patch.object(sdk._client, "get_state", new_callable=AsyncMock, return_value={
            "status": "idle",
            "model": "fantail2",
            "workspace": "/test",
            "message_count": 0,
        }):
            result = await sdk.get_state()
            assert result.status == "idle"
            assert result.model == "fantail2"

    @pytest.mark.asyncio
    async def test_get_messages_not_started(self) -> None:
        sdk = AutohandSDK()
        sdk._client = None
        with pytest.raises(RuntimeError, match="SDK not started"):
            await sdk.get_messages()

    @pytest.mark.asyncio
    async def test_get_messages(self) -> None:
        sdk = AutohandSDK()
        sdk._started = True
        with patch.object(sdk._client, "get_messages", new_callable=AsyncMock, return_value={"messages": []}):
            result = await sdk.get_messages(limit=10)
            assert result.messages == []

    @pytest.mark.asyncio
    async def test_get_models_not_started(self) -> None:
        sdk = AutohandSDK()
        sdk._client = None
        with pytest.raises(RuntimeError, match="SDK not started"):
            await sdk.get_models()

    @pytest.mark.asyncio
    async def test_get_models(self) -> None:
        sdk = AutohandSDK()
        sdk._started = True
        with patch.object(sdk._client, "get_models", new_callable=AsyncMock, return_value={"models": [{"id": "fantail2"}]}):
            result = await sdk.get_models()
            assert len(result) == 1
            assert result[0]["id"] == "fantail2"

    @pytest.mark.asyncio
    async def test_get_agents(self) -> None:
        sdk = AutohandSDK()
        sdk._started = True
        with patch.object(sdk._client, "get_agents", new_callable=AsyncMock, return_value={"agents": []}):
            result = await sdk.get_agents()
            assert result == []

    @pytest.mark.asyncio
    async def test_set_model_not_started(self) -> None:
        sdk = AutohandSDK()
        sdk._client = None
        with pytest.raises(RuntimeError, match="SDK not started"):
            await sdk.set_model("fantail2")

    @pytest.mark.asyncio
    async def test_set_model(self) -> None:
        sdk = AutohandSDK()
        sdk._started = True
        with patch.object(sdk._client, "set_model", new_callable=AsyncMock, return_value={"success": True}):
            result = await sdk.set_model("fantail2")
            assert result["success"]
            assert sdk.config.model == "fantail2"

    @pytest.mark.asyncio
    async def test_set_agent(self) -> None:
        sdk = AutohandSDK()
        sdk._started = True
        with patch.object(sdk._client, "set_agent", new_callable=AsyncMock, return_value={"success": True}):
            result = await sdk.set_agent("code-reviewer")
            assert result["success"]

    @pytest.mark.asyncio
    async def test_set_temperature(self) -> None:
        sdk = AutohandSDK()
        sdk._started = True
        with patch.object(sdk._client, "set_temperature", new_callable=AsyncMock, return_value={"success": True}):
            result = await sdk.set_temperature(0.5)
            assert result["success"]
            assert sdk.config.temperature == 0.5

    @pytest.mark.asyncio
    async def test_get_account_info(self) -> None:
        sdk = AutohandSDK()
        sdk._started = True
        with patch.object(sdk._client, "get_account_info", new_callable=AsyncMock, return_value={"email": "test@example.com"}):
            result = await sdk.get_account_info()
            assert result["email"] == "test@example.com"

    @pytest.mark.asyncio
    async def test_save_session(self) -> None:
        sdk = AutohandSDK()
        sdk._started = True
        with patch.object(sdk._client, "save_session", new_callable=AsyncMock, return_value={"success": True}):
            result = await sdk.save_session()
            assert result["success"]

    @pytest.mark.asyncio
    async def test_respond_to_permission(self) -> None:
        sdk = AutohandSDK()
        sdk._started = True
        with patch.object(sdk._client, "respond_to_permission", new_callable=AsyncMock, return_value={"success": True}):
            result = await sdk.respond_to_permission("req-123", decision="allow")
            assert result["success"]


class TestSDKIsRunning:
    """Tests for is_running method."""

    def test_is_running_not_started(self) -> None:
        sdk = AutohandSDK()
        assert not sdk.is_running()

    def test_is_running_started_but_client_not_running(self) -> None:
        sdk = AutohandSDK()
        sdk._started = True
        sdk._client = MagicMock()
        sdk._client.is_running.return_value = False
        assert not sdk.is_running()

    def test_is_running(self) -> None:
        sdk = AutohandSDK()
        sdk._started = True
        sdk._client = MagicMock()
        sdk._client.is_running.return_value = True
        assert sdk.is_running()
