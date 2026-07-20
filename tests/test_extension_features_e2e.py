"""End-to-end coverage for current CLI extension RPCs and notifications."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, TypeVar

import pytest
from pydantic import ValidationError

from autohand_sdk import AutohandSDK, SDKConfig

T = TypeVar("T")


def _feature_cli(
    tmp_path: Path,
    *,
    method: str,
    params: dict[str, Any],
    result: Any,
    notifications: list[dict[str, Any]] | None = None,
) -> Path:
    """Write a newline-delimited JSON-RPC CLI with one exact feature fixture."""
    fixture = json.dumps(
        {
            "method": method,
            "params": params,
            "result": result,
            "notifications": notifications or [],
        }
    )
    path = tmp_path / f"feature-cli-{len(list(tmp_path.iterdir()))}.py"
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        f"fixture = json.loads({fixture!r})\n"
        "for line in sys.stdin:\n"
        "    request = json.loads(line)\n"
        "    if request.get('method') == 'autohand.getState':\n"
        "        response = {'jsonrpc': '2.0', 'id': request.get('id'), 'result': {\n"
        "            'status': 'idle', 'sessionId': None, 'model': 'fake',\n"
        "            'workspace': '.', 'contextPercent': 0, 'messageCount': 0,\n"
        "        }}\n"
        "        print(json.dumps(response), flush=True)\n"
        "        for notification in fixture['notifications']:\n"
        "            print(json.dumps({'jsonrpc': '2.0', **notification}), flush=True)\n"
        "        continue\n"
        "    if (request.get('method') != fixture['method']\n"
        "            or request.get('params', {}) != fixture['params']):\n"
        "        print(json.dumps({'jsonrpc': '2.0', 'id': request.get('id'),\n"
        "            'error': {'code': -32602, 'message': 'unexpected method or params'}}),\n"
        "            flush=True)\n"
        "        continue\n"
        "    print(json.dumps({'jsonrpc': '2.0', 'id': request.get('id'),\n"
        "        'result': fixture['result']}), flush=True)\n",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


async def _with_sdk(
    cli_path: Path,
    run: Callable[[AutohandSDK], Awaitable[T]],
) -> T:
    async with AutohandSDK(SDKConfig(cli_path=str(cli_path), timeout=10_000)) as sdk:
        return await run(sdk)


@pytest.mark.asyncio
async def test_permission_acknowledgement_uses_spawned_cli(tmp_path: Path) -> None:
    """The public SDK sends the exact acknowledgement and validates its result."""
    cli = _feature_cli(
        tmp_path,
        method="autohand.permissionAcknowledged",
        params={"requestId": "permission-1"},
        result={"success": True},
    )

    result = await _with_sdk(cli, lambda sdk: sdk.acknowledge_permission("permission-1"))

    assert result.success is True


@pytest.mark.asyncio
async def test_permission_acknowledgement_rejects_malformed_result(tmp_path: Path) -> None:
    """Malformed acknowledgement results fail at the public SDK trust boundary."""
    cli = _feature_cli(
        tmp_path,
        method="autohand.permissionAcknowledged",
        params={"requestId": "permission-1"},
        result={"success": "yes"},
    )

    with pytest.raises(ValidationError):
        await _with_sdk(cli, lambda sdk: sdk.acknowledge_permission("permission-1"))


@pytest.mark.asyncio
async def test_directory_access_response_uses_spawned_cli(tmp_path: Path) -> None:
    """The SDK sends the exact directory grant and returns a typed result."""
    cli = _feature_cli(
        tmp_path,
        method="autohand.directoryAccessResponse",
        params={"requestId": "directory-1", "granted": True},
        result={"success": True},
    )

    result = await _with_sdk(cli, lambda sdk: sdk.respond_to_directory_access("directory-1", True))

    assert result.success is True


@pytest.mark.asyncio
async def test_directory_access_response_rejects_malformed_result(tmp_path: Path) -> None:
    """Malformed directory response results fail at the SDK trust boundary."""
    cli = _feature_cli(
        tmp_path,
        method="autohand.directoryAccessResponse",
        params={"requestId": "directory-1", "granted": False},
        result={"success": 1},
    )

    with pytest.raises(ValidationError):
        await _with_sdk(cli, lambda sdk: sdk.respond_to_directory_access("directory-1", False))


@pytest.mark.asyncio
async def test_directory_access_acknowledgement_uses_spawned_cli(tmp_path: Path) -> None:
    """The SDK acknowledges directory prompts through the exact CLI method."""
    cli = _feature_cli(
        tmp_path,
        method="autohand.directoryAccessAcknowledged",
        params={"requestId": "directory-1"},
        result={"success": True},
    )
    result = await _with_sdk(cli, lambda sdk: sdk.acknowledge_directory_access("directory-1"))
    assert result.success is True


@pytest.mark.asyncio
async def test_directory_access_acknowledgement_rejects_malformed_result(
    tmp_path: Path,
) -> None:
    """Malformed directory acknowledgements fail at the SDK trust boundary."""
    cli = _feature_cli(
        tmp_path,
        method="autohand.directoryAccessAcknowledged",
        params={"requestId": "directory-1"},
        result={},
    )
    with pytest.raises(ValidationError):
        await _with_sdk(cli, lambda sdk: sdk.acknowledge_directory_access("directory-1"))


@pytest.mark.asyncio
async def test_multi_file_change_decision_uses_spawned_cli(tmp_path: Path) -> None:
    """The SDK sends a typed selected-change decision and validates counts."""
    cli = _feature_cli(
        tmp_path,
        method="autohand.changesDecision",
        params={
            "batchId": "batch-1",
            "action": "accept_selected",
            "selectedChangeIds": ["change-1"],
        },
        result={
            "success": True,
            "appliedCount": 1,
            "skippedCount": 1,
            "errors": [{"changeId": "change-2", "error": "conflict"}],
        },
    )
    result = await _with_sdk(
        cli,
        lambda sdk: sdk.decide_changes(
            "batch-1", "accept_selected", selected_change_ids=["change-1"]
        ),
    )
    assert result.applied_count == 1
    assert result.errors[0].change_id == "change-2"


@pytest.mark.asyncio
async def test_multi_file_change_decision_rejects_malformed_count(tmp_path: Path) -> None:
    """String decision counts do not cross the SDK trust boundary."""
    cli = _feature_cli(
        tmp_path,
        method="autohand.changesDecision",
        params={"batchId": "batch-1", "action": "accept_all"},
        result={"success": True, "appliedCount": "one", "skippedCount": 0},
    )
    with pytest.raises(ValidationError):
        await _with_sdk(cli, lambda sdk: sdk.decide_changes("batch-1", "accept_all"))
