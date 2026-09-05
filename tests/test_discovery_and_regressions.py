"""Regression coverage for discovery APIs and lifecycle guarantees."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from textwrap import dedent
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

import autohand_sdk
from autohand_sdk import (
    AutohandSDK,
    GetSkillsRegistryResult,
    InstallSkillParams,
    McpGetServerConfigsResult,
    McpListServersResult,
    McpListToolsResult,
    RPCClient,
    SDKConfig,
    Transport,
)
from autohand_sdk.errors import TransportError
from autohand_sdk.transport import TransportOptions


def _write_executable(path: Path, source: str) -> Path:
    """Write one executable Python CLI fixture."""
    path.write_text(dedent(source).lstrip(), encoding="utf-8")
    path.chmod(0o755)
    return path


async def _wait_until(predicate: Callable[[], bool], *, timeout: float = 2.5) -> None:
    """Wait for an event-loop-driven condition without hiding a timeout."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate():
        if loop.time() >= deadline:
            raise TimeoutError("condition was not reached before timeout")
        await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_discovery_rpc_methods_preserve_exact_wire_contract() -> None:
    """All five discovery calls use exact CLI names and omit absent options."""
    client = RPCClient()
    request = AsyncMock(return_value={"success": True})
    with patch.object(client, "_request", request):
        await client.get_skills_registry()
        await client.get_skills_registry(False)
        await client.install_skill("typescript", "project", True)
        await client.list_mcp_servers()
        await client.list_mcp_tools()
        await client.list_mcp_tools("github")
        await client.get_mcp_server_configs()

    assert request.await_args_list == [
        (("autohand.getSkillsRegistry", {}),),
        (("autohand.getSkillsRegistry", {"forceRefresh": False}),),
        (
            (
                "autohand.installSkill",
                {"skillName": "typescript", "scope": "project", "force": True},
            ),
        ),
        (("autohand.mcp.listServers", {}),),
        (("autohand.mcp.listTools", {}),),
        (("autohand.mcp.listTools", {"serverName": "github"}),),
        (("autohand.mcp.getServerConfigs", {}),),
    ]


@pytest.mark.asyncio
async def test_sdk_discovery_results_are_typed() -> None:
    """The public SDK converts every discovery response into a typed result."""
    sdk = AutohandSDK()
    assert sdk._client is not None
    sdk._client.get_skills_registry = AsyncMock(
        return_value={
            "success": True,
            "skills": [
                {
                    "id": "typescript",
                    "name": "TypeScript",
                    "description": "Typed JavaScript",
                    "category": "language",
                    "downloadCount": 42,
                }
            ],
            "categories": [{"name": "language", "count": 1}],
        }
    )
    sdk._client.install_skill = AsyncMock(
        return_value={"success": False, "error": "already installed"}
    )
    sdk._client.list_mcp_servers = AsyncMock(
        return_value={"servers": [{"name": "github", "status": "connected", "toolCount": 3}]}
    )
    sdk._client.list_mcp_tools = AsyncMock(
        return_value={
            "tools": [{"name": "issues", "description": "List issues", "serverName": "github"}]
        }
    )
    sdk._client.get_mcp_server_configs = AsyncMock(
        return_value={
            "configs": [
                {
                    "name": "github",
                    "transport": "http",
                    "url": "https://example.test/mcp",
                    "autoConnect": True,
                }
            ]
        }
    )

    registry = await sdk.get_skills_registry(force_refresh=True)
    installed = await sdk.install_skill("typescript", "project")
    servers = await sdk.list_mcp_servers()
    tools = await sdk.list_mcp_tools("github")
    configs = await sdk.get_mcp_server_configs()

    assert isinstance(registry, GetSkillsRegistryResult)
    assert registry.skills[0].download_count == 42
    assert installed.success is False and installed.error == "already installed"
    assert isinstance(servers, McpListServersResult) and servers.servers[0].tool_count == 3
    assert isinstance(tools, McpListToolsResult) and tools.tools[0].server_name == "github"
    assert isinstance(configs, McpGetServerConfigsResult)
    assert configs.configs[0].auto_connect is True


def test_install_skill_scope_is_typed_and_validated() -> None:
    """Only CLI-supported user and project install scopes are accepted."""
    assert InstallSkillParams(skillName="x", scope="user").model_dump(
        by_alias=True, exclude_none=True
    ) == {"skillName": "x", "scope": "user"}
    with pytest.raises(ValidationError):
        InstallSkillParams(skillName="x", scope="global")


@pytest.mark.asyncio
async def test_plan_mode_is_applied_and_failed_start_rolls_back() -> None:
    """Documented plan mode is sent, and later config failure stops the CLI."""
    with patch("autohand_sdk.sdk.RPCClient") as client_class:
        client = AsyncMock()
        client.apply_flag_settings.side_effect = RuntimeError("apply failed")
        client_class.return_value = client
        sdk = AutohandSDK(plan_mode=True, features={"slashGoal": True})

        with pytest.raises(RuntimeError, match="apply failed"):
            await sdk.start()

    client.start.assert_awaited_once()
    client.set_plan_mode.assert_awaited_once_with(True)
    client.stop.assert_awaited_once()
    assert sdk._started is False


@pytest.mark.asyncio
async def test_event_consumers_receive_independent_copies() -> None:
    """A prompt stream and global subscriber both receive one notification."""
    client = RPCClient()
    release = asyncio.Event()

    async def request(method: str, _params: dict[str, object]) -> dict[str, object]:
        if method == "autohand.abort":
            client._handle_notification({"_method": "autohand.agentEnd"})
            return {"success": True}
        await release.wait()
        return {"content": "done"}

    with patch.object(client, "_request", side_effect=request):
        global_events = client.events()
        prompt_events = client.prompt({"message": "hello"})
        global_next = asyncio.create_task(anext(global_events))
        prompt_next = asyncio.create_task(anext(prompt_events))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        client._handle_notification(
            {"_method": "autohand.permissionRequest", "requestId": "permission-1"}
        )
        prompt_event, global_event = await asyncio.gather(prompt_next, global_next)
        release.set()
        await prompt_events.aclose()
        await global_events.aclose()

    assert prompt_event["request_id"] == "permission-1"
    assert global_event["request_id"] == "permission-1"


@pytest.mark.asyncio
async def test_stop_closes_blocked_event_consumers() -> None:
    """Stopping a client wakes global subscribers instead of leaving anext pending."""
    client = RPCClient()
    events = client.events()
    pending = asyncio.create_task(anext(events))
    await asyncio.sleep(0)

    with patch.object(client._transport, "stop", new_callable=AsyncMock):
        await client.stop()

    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(pending, timeout=0.1)


def test_compatibility_event_backlog_is_bounded() -> None:
    """Notifications cannot grow the private compatibility backlog forever."""
    client = RPCClient()
    for index in range(client._event_queue.maxsize + 25):
        client._publish_event({"type": "message_update", "index": index})

    assert client._event_queue.qsize() == client._event_queue.maxsize == 1_024
    assert client._event_queue.get_nowait()["index"] == 25


@pytest.mark.asyncio
async def test_closing_prompt_aborts_and_settles_request_task() -> None:
    """Stopping iteration aborts the accepted turn and leaves no request task."""
    client = RPCClient()
    started = asyncio.Event()
    request_task: asyncio.Task[object] | None = None
    methods: list[str] = []

    async def request(method: str, _params: dict[str, object]) -> dict[str, object]:
        nonlocal request_task
        methods.append(method)
        if method == "autohand.abort":
            client._handle_notification({"_method": "autohand.agentEnd"})
            return {"success": True}
        request_task = asyncio.current_task()
        started.set()
        return {"success": True}

    prompt_events = client.prompt({"message": "hello"})
    next_event = asyncio.create_task(anext(prompt_events))
    with patch.object(client, "_request", side_effect=request):
        await started.wait()
        client._handle_notification(
            {"_method": "autohand.messageUpdate", "messageId": "m1", "delta": "x"}
        )
        await next_event
        await prompt_events.aclose()

    assert methods == ["autohand.prompt", "autohand.abort"]
    assert request_task is not None and request_task.done()


def test_standard_autohand_binary_is_preferred_on_path() -> None:
    """Auto-detection supports the executable installed by the CLI package."""
    transport = Transport()
    with (
        patch.object(Path, "exists", return_value=False),
        patch("autohand_sdk.transport.shutil.which", return_value="/bin/autohand") as which,
    ):
        assert transport._detect_cli_binary() == "/bin/autohand"
    which.assert_called_once_with("autohand")


def test_every_documented_top_level_export_remains_resolvable() -> None:
    """Lazy package loading preserves the existing top-level API contract."""
    for name in autohand_sdk.__all__:
        assert getattr(autohand_sdk, name) is not None


def test_sdk_config_declares_plan_mode() -> None:
    """Plan mode is a real typed field instead of an ignored extra."""
    assert SDKConfig(plan_mode=False).plan_mode is False


@pytest.mark.asyncio
async def test_prompt_close_aborts_real_acknowledged_turn_without_late_event_leak(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Closing an ACK-first stream aborts, drains, and isolates the next prompt."""
    abort_file = tmp_path / "abort-seen"
    monkeypatch.setenv("TIN_ABORT_FILE", str(abort_file))
    cli_path = _write_executable(
        tmp_path / "ack-first-cli.py",
        r"""
        #!/usr/bin/env python3
        import json
        import os
        import sys
        import threading

        output_lock = threading.Lock()
        aborted = threading.Event()
        turn_count = 0

        def emit(message):
            with output_lock:
                print(json.dumps(message), flush=True)

        def notify(method, params=None):
            emit({"jsonrpc": "2.0", "method": method, "params": params or {}})

        def run_first_turn():
            notify("autohand.agentStart", {"sessionId": "first"})
            notify("autohand.messageUpdate", {"messageId": "m1", "delta": "first"})
            if not aborted.wait(0.4):
                notify("autohand.messageUpdate", {"messageId": "m1", "delta": "old-late"})
            notify("autohand.agentEnd", {"sessionId": "first", "reason": "aborted"})

        def run_second_turn():
            notify("autohand.agentStart", {"sessionId": "second"})
            notify("autohand.messageUpdate", {"messageId": "m2", "delta": "second"})
            notify("autohand.agentEnd", {"sessionId": "second", "reason": "completed"})

        for line in sys.stdin:
            request = json.loads(line)
            method = request.get("method")
            if method == "autohand.getState":
                emit({"jsonrpc": "2.0", "id": request.get("id"), "result": {"status": "idle"}})
            elif method == "autohand.prompt":
                turn_count += 1
                emit({"jsonrpc": "2.0", "id": request.get("id"), "result": {"success": True}})
                target = run_first_turn if turn_count == 1 else run_second_turn
                threading.Thread(target=target, daemon=True).start()
            elif method == "autohand.abort":
                aborted.set()
                with open(os.environ["TIN_ABORT_FILE"], "w", encoding="utf-8") as handle:
                    handle.write("seen")
                emit({"jsonrpc": "2.0", "id": request.get("id"), "result": {"success": True}})
        """,
    )

    client = RPCClient(SDKConfig(cli_path=str(cli_path), timeout=1_000))
    await client.start()
    try:
        first_stream = client.prompt({"message": "first"})
        first_events = [await anext(first_stream), await anext(first_stream)]
        await first_stream.aclose()

        second_events = [event async for event in client.prompt({"message": "second"})]
    finally:
        await client.stop()

    assert [event["type"] for event in first_events] == ["agent_start", "message_update"]
    assert abort_file.read_text(encoding="utf-8") == "seen"
    assert [event.get("delta") for event in second_events if event["type"] == "message_update"] == [
        "second"
    ]
    assert second_events[-1]["type"] == "agent_end"


@pytest.mark.asyncio
async def test_abandoned_prompt_timeout_retires_poisoned_transport() -> None:
    """A CLI that acknowledges abort but never ends the turn is stopped."""
    client = RPCClient()
    prompt_queue: asyncio.Queue[dict[str, object] | None] = asyncio.Queue()
    with (
        patch.object(client, "abort", new_callable=AsyncMock, return_value={"success": True}),
        patch.object(client, "stop", new_callable=AsyncMock) as stop,
        patch("autohand_sdk.rpc_client.PROMPT_CLEANUP_TIMEOUT_SECONDS", 0.01),
    ):
        await client._settle_abandoned_prompt(prompt_queue)

    stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_event_backlog_transfers_once_and_live_subscriber_queue_is_bounded() -> None:
    """A first subscriber inherits backlog once and every live queue stays bounded."""
    client = RPCClient()
    client._publish_event({"type": "message_update", "index": 0})
    client._publish_event({"type": "message_update", "index": 1})

    events = client.events()
    assert (await anext(events))["index"] == 0
    assert client._event_queue.empty()
    assert (await anext(events))["index"] == 1

    client._publish_event({"type": "message_update", "index": 2})
    assert (await anext(events))["index"] == 2
    assert client._event_queue.empty()

    subscriber = next(iter(client._event_subscribers))
    for index in range(3, 3 + subscriber.maxsize + 25):
        client._publish_event({"type": "message_update", "index": index})
    assert subscriber.qsize() == subscriber.maxsize == 1_024
    assert subscriber.get_nowait()["index"] == 28
    await events.aclose()

    prompt_queue: asyncio.Queue[dict[str, object] | None] = asyncio.Queue(maxsize=1_024)
    client._prompt_event_queue = prompt_queue
    for index in range(prompt_queue.maxsize + 25):
        client._publish_event({"type": "message_update", "index": index})
    assert prompt_queue.qsize() == 1
    assert prompt_queue.get_nowait() is None
    assert isinstance(client._prompt_error, TransportError)


@pytest.mark.asyncio
async def test_transport_coalesces_concurrent_start_and_cleans_cancelled_writer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Concurrent starts spawn once and cancellation cannot leak a pending callback."""
    pid_log = tmp_path / "pids.txt"
    monkeypatch.setenv("TIN_PID_LOG", str(pid_log))
    cli_path = _write_executable(
        tmp_path / "single-generation-cli.py",
        r"""
        #!/usr/bin/env python3
        import json
        import os
        import sys

        with open(os.environ["TIN_PID_LOG"], "a", encoding="utf-8") as handle:
            handle.write(f"{os.getpid()}\n")
        for line in sys.stdin:
            request = json.loads(line)
            print(json.dumps({
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "result": {"pid": os.getpid()},
            }), flush=True)
        """,
    )
    transport = Transport(TransportOptions(cli_path=str(cli_path), timeout=1_000))
    await asyncio.gather(*(transport.start() for _ in range(20)))
    try:
        result = await transport.request("autohand.getState", {})
        assert result["pid"] > 0
        assert len(pid_log.read_text(encoding="utf-8").splitlines()) == 1

        await transport._write_lock.acquire()
        request = asyncio.create_task(transport.request("autohand.getState", {}))
        await asyncio.sleep(0)
        assert len(transport._callbacks) == 1
        request.cancel()
        with pytest.raises(asyncio.CancelledError):
            await request
        assert transport._callbacks == {}
        transport._write_lock.release()
    finally:
        if transport._write_lock.locked():
            transport._write_lock.release()
        await transport.stop()


@pytest.mark.asyncio
async def test_unterminated_final_frame_reaps_live_child_and_restarts_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """EOF after a final JSON frame retires even a TERM-ignoring live child."""
    count_file = tmp_path / "generation.txt"
    monkeypatch.setenv("TIN_GENERATION_FILE", str(count_file))
    cli_path = _write_executable(
        tmp_path / "eof-cli.py",
        r"""
        #!/usr/bin/env python3
        import json
        import os
        import signal
        import sys
        import time
        from pathlib import Path

        count_file = Path(os.environ["TIN_GENERATION_FILE"])
        generation = int(count_file.read_text() if count_file.exists() else "0") + 1
        count_file.write_text(str(generation))
        if generation == 1:
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            request = json.loads(sys.stdin.readline())
            response = {"jsonrpc": "2.0", "id": request.get("id"), "result": {"generation": 1}}
            os.write(1, json.dumps(response).encode())
            os.close(1)
            time.sleep(10)
        else:
            for line in sys.stdin:
                request = json.loads(line)
                print(json.dumps({
                    "jsonrpc": "2.0",
                    "id": request.get("id"),
                    "result": {"generation": generation},
                }), flush=True)
        """,
    )
    transport = Transport(TransportOptions(cli_path=str(cli_path), timeout=1_000))
    await transport.start()
    first_process = transport._process
    assert first_process is not None
    try:
        assert await transport.request("autohand.getState", {}) == {"generation": 1}
        await _wait_until(lambda: not transport.is_running())

        await transport.start()
        assert first_process.returncode is not None
        assert await transport.request("autohand.getState", {}) == {"generation": 2}
        assert count_file.read_text(encoding="utf-8") == "2"
    finally:
        await transport.stop()


@pytest.mark.asyncio
async def test_transport_termination_resets_sdk_and_same_instance_restarts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected stdout closure clears both state layers and permits restart."""
    count_file = tmp_path / "sdk-generation.txt"
    monkeypatch.setenv("TIN_SDK_GENERATION_FILE", str(count_file))
    cli_path = _write_executable(
        tmp_path / "restartable-cli.py",
        r"""
        #!/usr/bin/env python3
        import json
        import os
        import sys
        import time
        from pathlib import Path

        count_file = Path(os.environ["TIN_SDK_GENERATION_FILE"])
        generation = int(count_file.read_text() if count_file.exists() else "0") + 1
        count_file.write_text(str(generation))
        for line in sys.stdin:
            request = json.loads(line)
            print(json.dumps({
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "result": {"status": "idle", "generation": generation},
            }), flush=True)
            if generation == 1:
                time.sleep(0.05)
                os.close(1)
                time.sleep(10)
        """,
    )
    sdk = AutohandSDK(SDKConfig(cli_path=str(cli_path), timeout=1_000))
    await sdk.start()
    assert sdk._client is not None
    first_process = sdk._client._transport._process
    assert first_process is not None and sdk._started
    try:
        await _wait_until(lambda: not sdk._started)
        assert not sdk._client._started

        await sdk.start()
        assert sdk.is_running()
        assert first_process.returncode is not None
        assert count_file.read_text(encoding="utf-8") == "2"
    finally:
        await sdk.stop()


@pytest.mark.asyncio
async def test_start_rejects_post_config_eof_and_same_instance_retries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A final config response cannot make a terminated SDK look started."""
    count_file = tmp_path / "post-config-generation.txt"
    pid_file = tmp_path / "post-config-pid.txt"
    monkeypatch.setenv("TIN_POST_CONFIG_GENERATION_FILE", str(count_file))
    monkeypatch.setenv("TIN_POST_CONFIG_PID_FILE", str(pid_file))
    cli_path = _write_executable(
        tmp_path / "post-config-eof-cli.py",
        r"""
        #!/usr/bin/env python3
        import json
        import os
        import signal
        import sys
        import time
        from pathlib import Path

        count_file = Path(os.environ["TIN_POST_CONFIG_GENERATION_FILE"])
        pid_file = Path(os.environ["TIN_POST_CONFIG_PID_FILE"])
        generation = int(count_file.read_text() if count_file.exists() else "0") + 1
        count_file.write_text(str(generation))

        if generation > 1 and pid_file.exists():
            previous_pid = int(pid_file.read_text())
            try:
                os.kill(previous_pid, 0)
            except ProcessLookupError:
                pass
            else:
                raise SystemExit("previous generation was not reaped")
        pid_file.write_text(str(os.getpid()))

        for line in sys.stdin:
            request = json.loads(line)
            method = request.get("method")
            result = {"status": "idle"} if method == "autohand.getState" else {"success": True}
            response = {"jsonrpc": "2.0", "id": request.get("id"), "result": result}
            if generation == 1 and method == "autohand.planModeSet":
                signal.signal(signal.SIGTERM, signal.SIG_IGN)
                os.write(1, json.dumps(response).encode())
                os.close(1)
                time.sleep(10)
            else:
                print(json.dumps(response), flush=True)
        """,
    )

    sdk = AutohandSDK(SDKConfig(cli_path=str(cli_path), timeout=1_000, plan_mode=True))
    try:
        with pytest.raises(TransportError, match="post-start configuration"):
            await sdk.start()

        assert not sdk._started
        assert sdk._client is not None and not sdk._client._started
        assert not sdk.is_running()

        await sdk.start()
        assert sdk.is_running()
        assert count_file.read_text(encoding="utf-8") == "2"
    finally:
        await sdk.stop()


@pytest.mark.asyncio
async def test_startup_failure_does_not_reenter_lifecycle_lock() -> None:
    """An already-exited process is retired directly while start owns its lock."""
    process = AsyncMock()
    process.returncode = 7
    process.stdin = None
    process.stdout = None
    process.stderr = None
    transport = Transport(TransportOptions(cli_path="/fixture"))
    with (
        patch("autohand_sdk.transport.asyncio.create_subprocess_exec", return_value=process),
        pytest.raises(TransportError, match="exited during startup"),
    ):
        await asyncio.wait_for(transport.start(), timeout=0.2)
