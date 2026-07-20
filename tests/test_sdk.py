"""Tests for the main SDK class."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autohand_sdk import AutohandSDK
from autohand_sdk.types import (
    AutomodeOperationResult,
    AutomodeStartResult,
    AutomodeStatusResult,
    AutoresearchStartResult,
    BrowserHandoffAttachResult,
    BrowserHandoffCreateResult,
    FeatureFlagSettings,
    GoalFeatureDisabledResult,
    GoalMutationResult,
    GoalSnapshot,
    ResetResult,
    SDKConfig,
    UpdateGoalParams,
)


@pytest.fixture(autouse=True)
def mock_cli_binary():
    """Mock CLI binary detection for all tests."""
    with patch(
        "autohand_sdk.transport.Transport._detect_cli_binary", return_value="/mock/autohand"
    ):
        yield


class TestSDKInitialization:
    """Tests for SDK initialization."""

    def test_default_init(self) -> None:
        sdk = AutohandSDK()
        assert sdk.config.model is None
        assert sdk._started is False
        assert sdk._skills == []

    def test_init_with_config(self) -> None:
        config = SDKConfig(model="fantail", cwd="/test", api_key="ah-test-key")
        sdk = AutohandSDK(config)
        assert sdk.config.model == "fantail"
        assert sdk.config.cwd == "/test"

    def test_init_with_kwargs(self) -> None:
        sdk = AutohandSDK(model="fantail", api_key="ah-test-key", debug=True)
        assert sdk.config.model == "fantail"
        assert sdk.config.debug is True

    def test_init_merges_kwargs(self) -> None:
        config = SDKConfig(model="fantail", api_key="ah-test-key")
        sdk = AutohandSDK(config, cwd="/merged")
        assert sdk.config.model == "fantail"
        assert sdk.config.cwd == "/merged"

    def test_init_with_skills(self) -> None:
        sdk = AutohandSDK(
            model="fantail", api_key="ah-test-key", skill_refs=["typescript", "react"]
        )
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

    def test_set_skills_while_started_preserves_live_client(self) -> None:
        sdk = AutohandSDK(skill_refs=["typescript"])
        original_client = sdk._client
        sdk._started = True

        with pytest.raises(RuntimeError, match=r"configured before start\(\)"):
            sdk.skills = ["react"]

        assert sdk._client is original_client
        assert sdk.skills == ["typescript"]
        assert sdk.config.skill_refs == ["typescript"]

    def test_set_skills_while_starting_preserves_client(self) -> None:
        sdk = AutohandSDK(skill_refs=["typescript"])
        original_client = sdk._client
        sdk._starting = True

        with pytest.raises(RuntimeError, match=r"configured before start\(\)"):
            sdk.skills = ["react"]

        assert sdk._client is original_client
        assert sdk.skills == ["typescript"]


class TestSDKLifecycle:
    """Tests for SDK lifecycle."""

    @pytest.mark.asyncio
    async def test_start(self) -> None:
        sdk = AutohandSDK()
        # Mock the entire client to avoid subprocess creation
        with patch("autohand_sdk.sdk.RPCClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance._started = True
            mock_instance.is_running = MagicMock(return_value=True)
            MockClient.return_value = mock_instance
            # Recreate sdk with mocked client
            sdk = AutohandSDK()
            await sdk.start()
            mock_instance.start.assert_called_once()
            assert sdk._started

    @pytest.mark.asyncio
    async def test_start_applies_feature_settings(self) -> None:
        with patch("autohand_sdk.sdk.RPCClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client._started = True
            mock_client.is_running = MagicMock(return_value=True)
            mock_client_class.return_value = mock_client
            sdk = AutohandSDK(
                features=FeatureFlagSettings(
                    slash_goal=True,
                    experimental_fork=True,
                )
            )

            await sdk.start()

        mock_client.start.assert_awaited_once()
        mock_client.apply_flag_settings.assert_awaited_once_with(
            {"features": {"slashGoal": True, "experimentalFork": True}}
        )
        assert sdk._started

    @pytest.mark.asyncio
    async def test_start_already_started(self) -> None:
        sdk = AutohandSDK()
        sdk._started = True
        with (
            patch.object(sdk._client, "is_running", return_value=True),
            patch.object(sdk._client, "start", new_callable=AsyncMock) as mock_start,
        ):
            await sdk.start()
            mock_start.assert_not_called()

    @pytest.mark.asyncio
    async def test_start_rebuilds_client_if_skills_changed(self) -> None:
        with patch("autohand_sdk.sdk.RPCClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.is_running = MagicMock(return_value=False)
            MockClient.return_value = mock_instance
            sdk = AutohandSDK()
            sdk.skills = ["typescript"]  # Set after init
            # After setting skills, client should be recreated
            assert sdk._config.skill_refs == sdk._skills

    @pytest.mark.asyncio
    async def test_start_does_not_replace_running_client_when_skills_drift(self) -> None:
        sdk = AutohandSDK(skill_refs=["typescript"])
        original_client = sdk._client
        assert original_client is not None
        sdk._skills = ["react"]

        with (
            patch.object(original_client, "is_running", return_value=True),
            pytest.raises(RuntimeError, match="CLI transport is running"),
        ):
            await sdk.start()

        assert sdk._client is original_client

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
        with (
            patch.object(AutohandSDK, "start", new_callable=AsyncMock) as mock_start,
            patch.object(AutohandSDK, "stop", new_callable=AsyncMock) as mock_stop,
        ):
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
        with patch.object(
            sdk._client,
            "abort",
            new_callable=AsyncMock,
            return_value={"success": True, "message": None},
        ):
            result = await sdk.abort("User cancelled")
            assert result.success is True

    @pytest.mark.asyncio
    async def test_reset_uses_exact_wire_contract_and_decodes_result(self) -> None:
        sdk = AutohandSDK()
        with patch.object(
            sdk._client,
            "_request",
            new_callable=AsyncMock,
            return_value={"sessionId": "session-new"},
        ) as request:
            result = await sdk.reset()

        request.assert_awaited_once_with("autohand.reset", {})
        assert result == ResetResult(session_id="session-new")

    @pytest.mark.asyncio
    async def test_create_browser_handoff_uses_exact_wire_and_decodes_result(self) -> None:
        sdk = AutohandSDK()
        wire_result = {
            "token": "token-1",
            "sessionId": "session-1",
            "workspaceRoot": "/workspace",
            "createdAt": "2026-07-20T00:00:00.000Z",
            "expiresAt": "2026-07-20T00:10:00.000Z",
            "url": "chrome-extension://ext/sidepanel.html?handoff=token-1",
        }
        with patch.object(
            sdk._client,
            "_request",
            new_callable=AsyncMock,
            return_value=wire_result,
        ) as request:
            result = await sdk.create_browser_handoff(
                extension_id="ext",
                install_url="https://example.test/install",
            )

        request.assert_awaited_once_with(
            "autohand.browserHandoff.create",
            {"extensionId": "ext", "installUrl": "https://example.test/install"},
        )
        assert result == BrowserHandoffCreateResult.model_validate(wire_result)
        assert result.workspace_root == "/workspace"

    @pytest.mark.asyncio
    async def test_attach_browser_handoff_uses_exact_wire_and_decodes_result(self) -> None:
        sdk = AutohandSDK()
        wire_result = {
            "success": True,
            "sessionId": "session-1",
            "workspaceRoot": "/workspace",
            "messageCount": 12,
        }
        with patch.object(
            sdk._client,
            "_request",
            new_callable=AsyncMock,
            return_value=wire_result,
        ) as request:
            result = await sdk.attach_browser_handoff("token-1")

        request.assert_awaited_once_with(
            "autohand.browserHandoff.attach",
            {"token": "token-1"},
        )
        assert result == BrowserHandoffAttachResult.model_validate(wire_result)
        assert result.message_count == 12

    @pytest.mark.asyncio
    async def test_attach_latest_browser_handoff_uses_exact_wire_and_decodes_result(self) -> None:
        sdk = AutohandSDK()
        wire_result = {"success": False}
        with patch.object(
            sdk._client,
            "_request",
            new_callable=AsyncMock,
            return_value=wire_result,
        ) as request:
            result = await sdk.attach_latest_browser_handoff()

        request.assert_awaited_once_with("autohand.browserHandoff.attachLatest", {})
        assert result == BrowserHandoffAttachResult(success=False)
        assert result.session_id is None

    @pytest.mark.asyncio
    async def test_start_automode_uses_exact_wire_and_decodes_result(self) -> None:
        sdk = AutohandSDK()
        wire_result = {"success": True, "sessionId": "auto-1"}
        with patch.object(
            sdk._client,
            "_request",
            new_callable=AsyncMock,
            return_value=wire_result,
        ) as request:
            result = await sdk.start_automode(
                "Ship the release",
                max_iterations=20,
                completion_promise="DONE",
                use_worktree=False,
                checkpoint_interval=5,
                max_runtime=60,
                max_cost=2.5,
            )

        request.assert_awaited_once_with(
            "autohand.automode.start",
            {
                "prompt": "Ship the release",
                "maxIterations": 20,
                "completionPromise": "DONE",
                "useWorktree": False,
                "checkpointInterval": 5,
                "maxRuntime": 60,
                "maxCost": 2.5,
            },
        )
        assert result == AutomodeStartResult(success=True, session_id="auto-1")

    @pytest.mark.asyncio
    async def test_get_automode_status_uses_exact_wire_and_decodes_result(self) -> None:
        sdk = AutohandSDK()
        wire_result = {
            "active": True,
            "paused": False,
            "state": {
                "sessionId": "auto-1",
                "status": "running",
                "currentIteration": 3,
                "maxIterations": 20,
                "filesCreated": 2,
                "filesModified": 4,
                "branch": "autohand/auto-1",
                "lastCheckpoint": {
                    "commit": "abc123",
                    "message": "iteration 2",
                    "timestamp": "2026-07-20T00:02:00.000Z",
                },
            },
        }
        with patch.object(
            sdk._client,
            "_request",
            new_callable=AsyncMock,
            return_value=wire_result,
        ) as request:
            result = await sdk.get_automode_status()

        request.assert_awaited_once_with("autohand.automode.status", {})
        assert result == AutomodeStatusResult.model_validate(wire_result)
        assert result.state is not None
        assert result.state.current_iteration == 3
        assert result.state.last_checkpoint is not None
        assert result.state.last_checkpoint.commit == "abc123"

    @pytest.mark.asyncio
    async def test_pause_automode_uses_exact_wire_and_decodes_result(self) -> None:
        sdk = AutohandSDK()
        with patch.object(
            sdk._client,
            "_request",
            new_callable=AsyncMock,
            return_value={"success": False, "error": "No active auto-mode session"},
        ) as request:
            result = await sdk.pause_automode()

        request.assert_awaited_once_with("autohand.automode.pause", {})
        assert result == AutomodeOperationResult(
            success=False,
            error="No active auto-mode session",
        )

    @pytest.mark.asyncio
    async def test_resume_automode_uses_exact_wire_and_decodes_result(self) -> None:
        sdk = AutohandSDK()
        with patch.object(
            sdk._client,
            "_request",
            new_callable=AsyncMock,
            return_value={"success": True},
        ) as request:
            result = await sdk.resume_automode()

        request.assert_awaited_once_with("autohand.automode.resume", {})
        assert result == AutomodeOperationResult(success=True)

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
        with patch.object(
            sdk._client,
            "get_state",
            new_callable=AsyncMock,
            return_value={
                "status": "idle",
                "model": "fantail",
                "workspace": "/test",
                "message_count": 0,
            },
        ):
            result = await sdk.get_state()
            assert result.status == "idle"
            assert result.model == "fantail"

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
        with patch.object(
            sdk._client, "get_messages", new_callable=AsyncMock, return_value={"messages": []}
        ):
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
        with patch.object(
            sdk._client,
            "get_models",
            new_callable=AsyncMock,
            return_value={"models": [{"id": "fantail"}]},
        ):
            result = await sdk.get_models()
            assert len(result) == 1
            assert result[0]["id"] == "fantail"

    @pytest.mark.asyncio
    async def test_get_agents(self) -> None:
        sdk = AutohandSDK()
        sdk._started = True
        with patch.object(
            sdk._client, "get_agents", new_callable=AsyncMock, return_value={"agents": []}
        ):
            result = await sdk.get_agents()
            assert result == []

    @pytest.mark.asyncio
    async def test_command_capability_and_run_helpers(self) -> None:
        sdk = AutohandSDK()
        sdk._started = True

        async def prompt_events(params):
            assert params["message"] == "/deep-research SDK parity"
            yield {"type": "message_update", "delta": "partial"}
            yield {"type": "message_end", "messageId": "m1", "content": "done"}

        with (
            patch.object(
                sdk._client,
                "get_agents",
                new_callable=AsyncMock,
                return_value={"commands": ["deep-research", "/autoresearch"]},
            ),
            patch.object(sdk._client, "prompt", side_effect=prompt_events),
        ):
            assert await sdk.supported_commands() == ["/deep-research", "/autoresearch"]
            assert await sdk.supports_command("deep-research") is True
            result = await sdk.deep_research("SDK parity")

        assert result.message_id == "m1"
        assert result.content == "done"

    @pytest.mark.asyncio
    async def test_autoresearch_command_formats_list_arguments(self) -> None:
        sdk = AutohandSDK()
        sdk._started = True
        messages: list[str] = []

        async def prompt_events(params):
            messages.append(params["message"])
            yield {"type": "message_end", "content": "started"}

        with patch.object(sdk._client, "prompt", side_effect=prompt_events):
            result = await sdk.command("autoresearch", ["improve", "latency"])

        assert messages == ["/autoresearch improve latency"]
        assert result.content == "started"

    @pytest.mark.asyncio
    async def test_set_model_not_started(self) -> None:
        sdk = AutohandSDK()
        sdk._client = None
        with pytest.raises(RuntimeError, match="SDK not started"):
            await sdk.set_model("fantail")

    @pytest.mark.asyncio
    async def test_set_model(self) -> None:
        sdk = AutohandSDK()
        sdk._started = True
        with patch.object(
            sdk._client, "set_model", new_callable=AsyncMock, return_value={"success": True}
        ):
            result = await sdk.set_model("fantail")
            assert result["success"]
            assert sdk.config.model == "fantail"

    @pytest.mark.asyncio
    async def test_set_agent(self) -> None:
        sdk = AutohandSDK()
        sdk._started = True
        with patch.object(
            sdk._client, "set_agent", new_callable=AsyncMock, return_value={"success": True}
        ):
            result = await sdk.set_agent("code-reviewer")
            assert result["success"]

    @pytest.mark.asyncio
    async def test_set_temperature(self) -> None:
        sdk = AutohandSDK()
        sdk._started = True
        with patch.object(
            sdk._client, "set_temperature", new_callable=AsyncMock, return_value={"success": True}
        ):
            result = await sdk.set_temperature(0.5)
            assert result["success"]
            assert sdk.config.temperature == 0.5

    @pytest.mark.asyncio
    async def test_apply_feature_settings(self) -> None:
        sdk = AutohandSDK()
        sdk._started = True
        settings = FeatureFlagSettings(slash_goal=True)
        with patch.object(
            sdk._client,
            "apply_flag_settings",
            new_callable=AsyncMock,
            return_value={"ok": True},
        ) as apply:
            result = await sdk.apply_feature_settings(settings)

        assert result == {"ok": True}
        apply.assert_awaited_once_with({"features": {"slashGoal": True}})
        assert sdk.config.features == settings

    @pytest.mark.asyncio
    async def test_get_account_info(self) -> None:
        sdk = AutohandSDK()
        sdk._started = True
        with patch.object(
            sdk._client,
            "get_account_info",
            new_callable=AsyncMock,
            return_value={"email": "test@example.com"},
        ):
            result = await sdk.get_account_info()
            assert result["email"] == "test@example.com"

    @pytest.mark.asyncio
    async def test_save_session(self) -> None:
        sdk = AutohandSDK()
        sdk._started = True
        with patch.object(
            sdk._client, "save_session", new_callable=AsyncMock, return_value={"success": True}
        ):
            result = await sdk.save_session()
            assert result["success"]

    @pytest.mark.asyncio
    async def test_persistent_goal_helpers_are_typed_and_camel_case(self) -> None:
        sdk = AutohandSDK()
        sdk._started = True
        snapshot = {
            "version": 1,
            "goal": None,
            "queue": [],
            "completed": [],
            "updatedAt": 10,
        }
        mutation = {"ok": True, "goal": None, "queue": []}
        template = {
            "name": "ship",
            "path": "goals/ship.md",
            "aliases": [],
            "allowCommands": True,
            "requiredPlaceholders": [],
            "requiredFlags": [],
            "requiresArgs": False,
        }
        with (
            patch.object(sdk._client, "get_goal", new_callable=AsyncMock, return_value=snapshot),
            patch.object(
                sdk._client,
                "create_goal",
                new_callable=AsyncMock,
                return_value=mutation,
            ) as create,
            patch.object(
                sdk._client,
                "update_goal",
                new_callable=AsyncMock,
                return_value=mutation,
            ) as update,
            patch.object(
                sdk._client,
                "queue_goal",
                new_callable=AsyncMock,
                return_value=mutation,
            ) as queue,
            patch.object(
                sdk._client,
                "start_queued_goal",
                new_callable=AsyncMock,
                return_value=mutation,
            ) as start_queued,
            patch.object(
                sdk._client,
                "list_goal_templates",
                new_callable=AsyncMock,
                return_value=[template],
            ),
        ):
            current = await sdk.get_goal()
            created = await sdk.create_goal("Ship parity", token_budget=1000)
            updated = await sdk.update_goal(UpdateGoalParams(token_budget=None))
            queued = await sdk.queue_goal("Document parity", time_budget_seconds=60)
            started = await sdk.start_queued_goal()
            templates = await sdk.list_goal_templates()

        assert isinstance(current, GoalSnapshot)
        assert current.updated_at == 10
        assert isinstance(created, GoalMutationResult)
        create.assert_awaited_once_with({"objective": "Ship parity", "tokenBudget": 1000})
        update.assert_awaited_once_with({"tokenBudget": None})
        assert isinstance(updated, GoalMutationResult)
        queue.assert_awaited_once_with({"objective": "Document parity", "timeBudgetSeconds": 60})
        assert isinstance(queued, GoalMutationResult)
        start_queued.assert_awaited_once_with()
        assert isinstance(started, GoalMutationResult)
        assert templates[0].allow_commands is True

    @pytest.mark.asyncio
    async def test_goal_feature_disabled_result_is_typed(self) -> None:
        sdk = AutohandSDK()
        sdk._started = True
        with patch.object(
            sdk._client,
            "clear_goal",
            new_callable=AsyncMock,
            return_value={"ok": False, "message": "slashGoal disabled"},
        ):
            result = await sdk.clear_goal()

        assert isinstance(result, GoalFeatureDisabledResult)

    @pytest.mark.asyncio
    async def test_start_autoresearch_returns_typed_result(self) -> None:
        sdk = AutohandSDK()
        sdk._started = True
        response = {
            "success": True,
            "instruction": "Run the next experiment",
            "active": True,
            "statusText": "Ready",
            "runsLogged": 0,
        }
        with patch.object(
            sdk._client, "start_autoresearch", new_callable=AsyncMock, return_value=response
        ) as start:
            result = await sdk.start_autoresearch(
                objective="Improve latency",
                max_iterations=5,
                measure_command="uv run pytest",
            )

        assert isinstance(result, AutoresearchStartResult)
        assert result.instruction == "Run the next experiment"
        start.assert_awaited_once_with(
            {
                "objective": "Improve latency",
                "maxIterations": 5,
                "measureCommand": "uv run pytest",
            }
        )

    @pytest.mark.asyncio
    async def test_autoresearch_ledger_helpers_return_typed_results(self) -> None:
        sdk = AutohandSDK()
        sdk._started = True
        with (
            patch.object(
                sdk._client,
                "get_autoresearch_history",
                new_callable=AsyncMock,
                return_value={"success": True, "attempts": []},
            ),
            patch.object(
                sdk._client,
                "get_autoresearch_pareto",
                new_callable=AsyncMock,
                return_value={"success": True, "attemptIds": ["a1"]},
            ),
            patch.object(
                sdk._client,
                "prune_autoresearch",
                new_callable=AsyncMock,
                return_value={
                    "success": True,
                    "applied": False,
                    "candidates": [],
                    "bytesFreed": 0,
                    "remainingBytes": 12,
                },
            ),
        ):
            history = await sdk.get_autoresearch_history()
            pareto = await sdk.get_autoresearch_pareto()
            prune = await sdk.prune_autoresearch(dry_run=True)

        assert history.attempts == []
        assert pareto.attempt_ids == ["a1"]
        assert prune.remaining_bytes == 12

    @pytest.mark.asyncio
    async def test_respond_to_permission(self) -> None:
        sdk = AutohandSDK()
        sdk._started = True
        with patch.object(
            sdk._client,
            "respond_to_permission",
            new_callable=AsyncMock,
            return_value={"success": True},
        ):
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
