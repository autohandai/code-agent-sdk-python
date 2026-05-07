"""Tests for the RPC client."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autohand_sdk.errors import TransportError
from autohand_sdk.rpc_client import RPC_METHODS, RPCClient
from autohand_sdk.types import ContextSettings, PermissionSettings, SDKConfig, SessionSettings


class TestRPCClientInitialization:
    """Tests for RPC client initialization."""

    def test_default_init(self) -> None:
        client = RPCClient()
        assert client._transport is not None
        assert not client._started

    def test_init_with_config(self) -> None:
        config = SDKConfig(model="fantail2")
        client = RPCClient(config)
        assert client.config.model == "fantail2"

    def test_init_with_skills(self) -> None:
        config = SDKConfig(skill_refs=["typescript", "./skills/custom/SKILL.md"])
        client = RPCClient(config)
        assert client._transport.options.skills == ["typescript", "custom"]
        assert client._transport.options.skill_files == ["./skills/custom/SKILL.md"]

    def test_init_processes_skill_names(self) -> None:
        config = SDKConfig(skill_refs=["typescript", { "name": "my-skill", "path": "./skills/SKILL.md" }])
        client = RPCClient(config)
        # Names are extracted
        assert "typescript" in client._transport.options.skills
        assert "my-skill" in client._transport.options.skills
        assert client._transport.options.skill_files == ["./skills/SKILL.md"]

    def test_init_maps_config_to_transport_options(self) -> None:
        config = SDKConfig(
            model="fantail2",
            temperature=0.2,
            max_iterations=5,
            max_runtime=10,
            max_cost=1.5,
            sys_prompt="system",
            append_sys_prompt="append",
            yolo="git status",
            yolo_timeout=30,
            add_dir=["../shared"],
            additional_directories=["../shared", "../docs"],
            extra_args=["--no-banner"],
            copy_skill_files=False,
            permission_mode="interactive",
            session=SessionSettings(
                persist_session=True,
                session_id="session-1",
                resume=True,
                continue_=True,
                session_path=".autohand/session.json",
                auto_save_interval=60,
            ),
            context=ContextSettings(
                context_compact=True,
                max_tokens=1000,
                compression_threshold=0.7,
                summarization_threshold=0.8,
            ),
            permissions=PermissionSettings(
                mode="default",
                allow_list=["read"],
                deny_list=["delete"],
            ),
        )

        client = RPCClient(config)
        opts = client._transport.options
        assert opts.model == "fantail2"
        assert opts.temperature == 0.2
        assert opts.max_iterations == 5
        assert opts.max_runtime == 10
        assert opts.max_cost == 1.5
        assert opts.sys_prompt == "system"
        assert opts.append_sys_prompt == "append"
        assert opts.yolo == "git status"
        assert opts.yolo_timeout == 30
        assert opts.add_dir == ["../shared", "../docs"]
        assert opts.extra_args == ["--no-banner"]
        assert opts.copy_skill_files is False
        assert opts.permission_mode == "default"
        assert opts.persist_session is True
        assert opts.session_id == "session-1"
        assert opts.resume is True
        assert opts.continue_session is True
        assert opts.session_path == ".autohand/session.json"
        assert opts.auto_save_interval == 60
        assert opts.context_compact is True
        assert opts.max_tokens == 1000
        assert opts.compression_threshold == 0.7
        assert opts.summarization_threshold == 0.8
        assert opts.permission_allow_list == ["read"]
        assert opts.permission_deny_list == ["delete"]

    def test_init_with_env_vars(self) -> None:
        config = SDKConfig(
            env_vars={"AUTOHAND_DEBUG": "1", "AUTOHAND_YES": "1"}
        )
        client = RPCClient(config)
        assert client._transport.options.env_vars == {
            "AUTOHAND_DEBUG": "1",
            "AUTOHAND_YES": "1",
        }


class TestRPCClientLifecycle:
    """Tests for RPC client lifecycle."""

    @pytest.mark.asyncio
    async def test_start_not_started(self) -> None:
        client = RPCClient()
        with patch.object(client._transport, "start", new_callable=AsyncMock) as mock_start:
            await client.start()
            mock_start.assert_called_once()
            assert client._started

    @pytest.mark.asyncio
    async def test_start_runs_startup_check_when_transport_running(self) -> None:
        client = RPCClient()
        client._transport.is_running = MagicMock(return_value=True)
        with patch.object(client._transport, "start", new_callable=AsyncMock), \
             patch.object(client, "_request", new_callable=AsyncMock, return_value={"status": "idle"}) as mock_request:
            await client.start()

        mock_request.assert_called_once_with(RPC_METHODS["get_state"], {})
        assert client._started

    @pytest.mark.asyncio
    async def test_start_wraps_startup_check_failure(self) -> None:
        client = RPCClient()
        client._transport.is_running = MagicMock(return_value=True)
        client._transport._stderr_lines = ["bad startup"]
        with (
            patch.object(client._transport, "start", new_callable=AsyncMock),
            patch.object(client._transport, "stop", new_callable=AsyncMock) as mock_stop,
            patch.object(
                client,
                "_request",
                new_callable=AsyncMock,
                side_effect=RuntimeError("boom"),
            ),
            pytest.raises(TransportError, match="CLI startup check failed"),
        ):
            await client.start()

        mock_stop.assert_called_once()
        assert not client._started

    @pytest.mark.asyncio
    async def test_start_skips_startup_check_when_disabled(self) -> None:
        client = RPCClient(SDKConfig(startup_check=False))
        client._transport.is_running = MagicMock(return_value=True)
        with patch.object(client._transport, "start", new_callable=AsyncMock), \
             patch.object(client, "_request", new_callable=AsyncMock) as mock_request:
            await client.start()

        mock_request.assert_not_called()
        assert client._started

    @pytest.mark.asyncio
    async def test_start_already_started(self) -> None:
        client = RPCClient()
        client._started = True
        with patch.object(client._transport, "start", new_callable=AsyncMock) as mock_start:
            await client.start()
            mock_start.assert_not_called()

    @pytest.mark.asyncio
    async def test_stop(self) -> None:
        client = RPCClient()
        with patch.object(client._transport, "stop", new_callable=AsyncMock) as mock_stop:
            await client.stop()
            mock_stop.assert_called_once()
            assert not client._started

    @pytest.mark.asyncio
    async def test_stop_no_transport(self) -> None:
        client = RPCClient()
        client._transport = None
        # Should not raise
        await client.stop()


class TestRPCClientMethods:
    """Tests for RPC client methods."""

    @pytest.mark.asyncio
    async def test_initialize(self) -> None:
        client = RPCClient()
        with patch.object(client, "_request", new_callable=AsyncMock, return_value={"success": True}):
            result = await client.initialize({"model": "fantail2"})
            assert result["success"]

    @pytest.mark.asyncio
    async def test_abort(self) -> None:
        client = RPCClient()
        with patch.object(client, "_request", new_callable=AsyncMock, return_value={"success": True}):
            result = await client.abort()
            assert result["success"]

    @pytest.mark.asyncio
    async def test_abort_with_params(self) -> None:
        client = RPCClient()
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_request:
            await client.abort({"reason": "User cancelled"})
            mock_request.assert_called_with(RPC_METHODS["abort"], {"reason": "User cancelled"})

    @pytest.mark.asyncio
    async def test_respond_to_permission(self) -> None:
        client = RPCClient()
        with patch.object(client, "_request", new_callable=AsyncMock, return_value={"success": True}):
            result = await client.respond_to_permission({"request_id": "123", "decision": "allow"})
            assert result["success"]

    @pytest.mark.asyncio
    async def test_get_state(self) -> None:
        client = RPCClient()
        with patch.object(client, "_request", new_callable=AsyncMock, return_value={
            "status": "idle",
            "model": "fantail2",
            "workspace": "/test",
        }):
            result = await client.get_state()
            assert result["status"] == "idle"

    @pytest.mark.asyncio
    async def test_get_messages(self) -> None:
        client = RPCClient()
        with patch.object(client, "_request", new_callable=AsyncMock, return_value={"messages": []}):
            result = await client.get_messages()
            assert result == {"messages": []}

    @pytest.mark.asyncio
    async def test_get_models(self) -> None:
        client = RPCClient()
        with patch.object(client, "_request", new_callable=AsyncMock, return_value={"models": [{"id": "fantail2"}]}):
            result = await client.get_models()
            assert result == {"models": [{"id": "fantail2"}]}

    @pytest.mark.asyncio
    async def test_get_agents(self) -> None:
        client = RPCClient()
        with patch.object(client, "_request", new_callable=AsyncMock, return_value={"agents": []}):
            result = await client.get_agents()
            assert result == {"agents": []}

    @pytest.mark.asyncio
    async def test_set_model(self) -> None:
        client = RPCClient()
        with patch.object(client, "_request", new_callable=AsyncMock, return_value={"success": True}):
            result = await client.set_model("fantail2")
            assert result["success"]

    @pytest.mark.asyncio
    async def test_set_agent(self) -> None:
        client = RPCClient()
        with patch.object(client, "_request", new_callable=AsyncMock, return_value={"success": True}):
            result = await client.set_agent("code-reviewer")
            assert result["success"]

    @pytest.mark.asyncio
    async def test_set_temperature(self) -> None:
        client = RPCClient()
        with patch.object(client, "_request", new_callable=AsyncMock, return_value={"success": True}):
            result = await client.set_temperature(0.5)
            assert result["success"]

    @pytest.mark.asyncio
    async def test_get_account_info(self) -> None:
        client = RPCClient()
        with patch.object(client, "_request", new_callable=AsyncMock, return_value={"email": "test@example.com"}):
            result = await client.get_account_info()
            assert result["email"] == "test@example.com"

    @pytest.mark.asyncio
    async def test_save_session(self) -> None:
        client = RPCClient()
        with patch.object(client, "_request", new_callable=AsyncMock, return_value={"success": True}):
            result = await client.save_session()
            assert result["success"]

    @pytest.mark.asyncio
    async def test_request_not_initialized(self) -> None:
        client = RPCClient()
        client._transport = None
        with pytest.raises(RuntimeError, match="Transport not initialized"):
            await client._request("prompt", {})

    @pytest.mark.asyncio
    async def test_prompt(self) -> None:
        client = RPCClient()
        with patch.object(client, "_request", new_callable=AsyncMock, return_value={"content": "Hello", "session_id": "123"}):
            events = []
            async for event in client.prompt({"message": "Hi"}):
                events.append(event)
            assert len(events) == 3
            assert events[0]["type"] == "agent_start"
            assert events[1]["type"] == "message_end"
            assert events[2]["type"] == "agent_end"

    @pytest.mark.asyncio
    async def test_prompt_drains_stale_events_before_request(self) -> None:
        client = RPCClient()
        client._event_queue.put_nowait({"type": "message_update", "delta": "stale"})

        with patch.object(client, "_request", new_callable=AsyncMock, return_value={"content": "fresh"}):
            events = [event async for event in client.prompt({"message": "Hi"})]

        assert all(event.get("delta") != "stale" for event in events)
        assert [event["type"] for event in events] == [
            "agent_start",
            "message_end",
            "agent_end",
        ]

    @pytest.mark.asyncio
    async def test_prompt_streams_cli_notifications(self, tmp_path: Path) -> None:
        cli_path = tmp_path / "stream-cli.py"
        cli_path.write_text(
            "#!/usr/bin/env python3\n"
            "import json, sys\n"
            "for line in sys.stdin:\n"
            "    req = json.loads(line)\n"
            "    print(json.dumps({'jsonrpc': '2.0', 'method': 'autohand.agentStart', 'params': {\n"
            "        'sessionId': 's1', 'model': 'fantail2', 'workspace': '.', 'timestamp': 't1'\n"
            "    }}), flush=True)\n"
            "    print(json.dumps({'jsonrpc': '2.0', 'method': 'autohand.messageUpdate', 'params': {\n"
            "        'messageId': 'm1', 'delta': 'hello', 'timestamp': 't2'\n"
            "    }}), flush=True)\n"
            "    print(json.dumps({'jsonrpc': '2.0', 'method': 'autohand.messageEnd', 'params': {\n"
            "        'messageId': 'm1', 'content': 'hello', 'timestamp': 't3'\n"
            "    }}), flush=True)\n"
            "    print(json.dumps({'jsonrpc': '2.0', 'method': 'autohand.turnEnd', 'params': {\n"
            "        'turnId': 'turn1', 'timestamp': 't4'\n"
            "    }}), flush=True)\n"
            "    print(json.dumps({'jsonrpc': '2.0', 'id': req.get('id'), 'result': {'success': True}}), flush=True)\n",
            encoding="utf-8",
        )
        cli_path.chmod(0o755)

        client = RPCClient(SDKConfig(cli_path=str(cli_path), timeout=1000))
        await client.start()
        try:
            events = [event async for event in client.prompt({"message": "Hi"})]
        finally:
            await client.stop()

        assert [event["type"] for event in events] == [
            "agent_start",
            "message_update",
            "message_end",
            "turn_end",
            "agent_end",
        ]
        assert events[0]["session_id"] == "s1"
        assert events[1]["message_id"] == "m1"


class TestRPCClientIsRunning:
    """Tests for is_running method."""

    def test_is_running_no_transport(self) -> None:
        client = RPCClient()
        client._transport = None
        assert not client.is_running()

    def test_is_running_transport_running(self) -> None:
        client = RPCClient()
        client._transport = MagicMock()
        client._transport.is_running.return_value = True
        assert client.is_running()

    def test_is_running_transport_not_running(self) -> None:
        client = RPCClient()
        client._transport = MagicMock()
        client._transport.is_running.return_value = False
        assert not client.is_running()
