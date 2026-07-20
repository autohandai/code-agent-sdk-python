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


@pytest.mark.asyncio
async def test_session_history_uses_spawned_cli(tmp_path: Path) -> None:
    """The SDK returns paginated typed session history."""
    cli = _feature_cli(
        tmp_path,
        method="autohand.getHistory",
        params={"page": 2, "pageSize": 10},
        result={
            "sessions": [
                {
                    "sessionId": "session-1",
                    "createdAt": "t1",
                    "lastActiveAt": "t2",
                    "projectName": "tin-wrapper",
                    "model": "fantail",
                    "messageCount": 4,
                    "status": "completed",
                }
            ],
            "currentPage": 2,
            "totalPages": 4,
            "totalItems": 31,
        },
    )
    result = await _with_sdk(cli, lambda sdk: sdk.get_history(page=2, page_size=10))
    assert result.sessions[0].session_id == "session-1"
    assert result.total_items == 31


@pytest.mark.asyncio
async def test_session_history_rejects_unknown_status(tmp_path: Path) -> None:
    """Unknown session statuses fail result validation."""
    cli = _feature_cli(
        tmp_path,
        method="autohand.getHistory",
        params={},
        result={
            "sessions": [
                {
                    "sessionId": "session-1",
                    "createdAt": "t1",
                    "lastActiveAt": "t2",
                    "projectName": "tin-wrapper",
                    "model": "fantail",
                    "messageCount": 4,
                    "status": "deleted",
                }
            ],
            "currentPage": 1,
            "totalPages": 1,
            "totalItems": 1,
        },
    )
    with pytest.raises(ValidationError):
        await _with_sdk(cli, lambda sdk: sdk.get_history())


@pytest.mark.asyncio
async def test_session_details_use_spawned_cli(tmp_path: Path) -> None:
    """The SDK returns typed session metadata and messages."""
    cli = _feature_cli(
        tmp_path,
        method="autohand.getSession",
        params={"sessionId": "session-1"},
        result={
            "success": True,
            "sessionId": "session-1",
            "projectName": "tin-wrapper",
            "model": "fantail",
            "messageCount": 1,
            "status": "completed",
            "createdAt": "t1",
            "lastActiveAt": "t2",
            "summary": "Done",
            "messages": [
                {
                    "id": "message-1",
                    "role": "assistant",
                    "content": "Done",
                    "timestamp": "t2",
                    "toolCalls": [{"id": "tool-1", "name": "write_file", "args": {"path": "a.py"}}],
                }
            ],
            "workspaceRoot": "/workspace",
        },
    )
    result = await _with_sdk(cli, lambda sdk: sdk.get_session("session-1"))
    assert result.success is True
    assert result.messages[0].tool_calls[0].name == "write_file"


@pytest.mark.asyncio
async def test_missing_session_result_is_typed(tmp_path: Path) -> None:
    """A missing saved session remains a typed failure result."""
    cli = _feature_cli(
        tmp_path,
        method="autohand.getSession",
        params={"sessionId": "missing"},
        result={"success": False, "error": "Session not found"},
    )
    result = await _with_sdk(cli, lambda sdk: sdk.get_session("missing"))
    assert result.success is False
    assert result.error == "Session not found"


@pytest.mark.asyncio
async def test_successful_session_details_require_complete_payload(tmp_path: Path) -> None:
    """Incomplete successful session payloads fail result validation."""
    cli = _feature_cli(
        tmp_path,
        method="autohand.getSession",
        params={"sessionId": "session-1"},
        result={"success": True, "sessionId": "session-1"},
    )
    with pytest.raises(ValidationError):
        await _with_sdk(cli, lambda sdk: sdk.get_session("session-1"))


@pytest.mark.asyncio
async def test_session_attachment_uses_spawned_cli(tmp_path: Path) -> None:
    """The SDK attaches to a saved session and returns typed metadata."""
    cli = _feature_cli(
        tmp_path,
        method="autohand.session.attach",
        params={"sessionId": "session-1"},
        result={
            "success": True,
            "sessionId": "session-1",
            "workspaceRoot": "/workspace",
            "messageCount": 8,
        },
    )
    result = await _with_sdk(cli, lambda sdk: sdk.attach_session("session-1"))
    assert result.workspace_root == "/workspace"


@pytest.mark.asyncio
async def test_session_attachment_rejects_malformed_error(tmp_path: Path) -> None:
    """Non-string attachment errors fail result validation."""
    cli = _feature_cli(
        tmp_path,
        method="autohand.session.attach",
        params={"sessionId": "session-1"},
        result={"success": False, "error": 404},
    )
    with pytest.raises(ValidationError):
        await _with_sdk(cli, lambda sdk: sdk.attach_session("session-1"))


@pytest.mark.asyncio
async def test_timed_yolo_uses_canonical_spawned_cli_method(tmp_path: Path) -> None:
    """The SDK sends timed YOLO settings through the canonical method."""
    cli = _feature_cli(
        tmp_path,
        method="autohand.yoloSet",
        params={"pattern": "*", "timeoutSeconds": 300},
        result={"success": True, "expiresIn": 300},
    )
    result = await _with_sdk(cli, lambda sdk: sdk.set_yolo("*", timeout_seconds=300))
    assert result.expires_in == 300


@pytest.mark.asyncio
async def test_timed_yolo_supports_compatibility_alias(tmp_path: Path) -> None:
    """Older dotted YOLO RPCs remain explicitly available."""
    cli = _feature_cli(
        tmp_path,
        method="autohand.yolo.set",
        params={"pattern": "bash:*", "timeoutSeconds": 60},
        result={"success": True, "expiresIn": 60},
    )
    result = await _with_sdk(cli, lambda sdk: sdk.set_yolo_compat("bash:*", timeout_seconds=60))
    assert result.expires_in == 60


@pytest.mark.asyncio
async def test_timed_yolo_rejects_malformed_expiration(tmp_path: Path) -> None:
    """Non-numeric expiration values fail result validation."""
    cli = _feature_cli(
        tmp_path,
        method="autohand.yoloSet",
        params={"pattern": ""},
        result={"success": True, "expiresIn": "never"},
    )
    with pytest.raises(ValidationError):
        await _with_sdk(cli, lambda sdk: sdk.set_yolo(""))


@pytest.mark.asyncio
async def test_vscode_mcp_tool_registration_uses_spawned_cli(tmp_path: Path) -> None:
    """The SDK sends validated VS Code MCP descriptors to the CLI."""
    tools = [
        {
            "name": "vscode.findReferences",
            "description": "Find references",
            "serverName": "vscode",
            "inputSchema": {
                "type": "object",
                "properties": {"symbol": {"type": "string"}},
                "required": ["symbol"],
            },
        }
    ]
    cli = _feature_cli(
        tmp_path,
        method="autohand.mcp.setVscodeTools",
        params={"tools": tools},
        result={"success": True},
    )
    result = await _with_sdk(cli, lambda sdk: sdk.set_vscode_mcp_tools(tools))
    assert result.success is True


@pytest.mark.asyncio
async def test_vscode_mcp_tool_registration_rejects_malformed_result(tmp_path: Path) -> None:
    """Malformed registration acknowledgements fail result validation."""
    cli = _feature_cli(
        tmp_path,
        method="autohand.mcp.setVscodeTools",
        params={"tools": []},
        result={"success": None},
    )
    with pytest.raises(ValidationError):
        await _with_sdk(cli, lambda sdk: sdk.set_vscode_mcp_tools([]))


@pytest.mark.asyncio
async def test_mcp_invocation_response_uses_spawned_cli(tmp_path: Path) -> None:
    """The SDK resolves a VS Code-hosted MCP invocation through the CLI."""
    cli = _feature_cli(
        tmp_path,
        method="autohand.mcp.invokeResponse",
        params={"requestId": "mcp-1", "success": True, "result": '{"matches":3}'},
        result={"success": True},
    )
    result = await _with_sdk(
        cli,
        lambda sdk: sdk.respond_to_mcp_invocation("mcp-1", success=True, result='{"matches":3}'),
    )
    assert result.success is True


@pytest.mark.asyncio
async def test_mcp_invocation_response_rejects_malformed_ack(tmp_path: Path) -> None:
    """Malformed MCP response acknowledgements fail validation."""
    cli = _feature_cli(
        tmp_path,
        method="autohand.mcp.invokeResponse",
        params={"requestId": "mcp-1", "success": False, "error": "failed"},
        result={"success": "true"},
    )
    with pytest.raises(ValidationError):
        await _with_sdk(
            cli,
            lambda sdk: sdk.respond_to_mcp_invocation("mcp-1", success=False, error="failed"),
        )


@pytest.mark.asyncio
async def test_learning_recommendations_use_spawned_cli(tmp_path: Path) -> None:
    """The SDK returns typed project learning recommendations."""
    cli = _feature_cli(
        tmp_path,
        method="autohand.learn.recommend",
        params={"deep": True},
        result={
            "success": True,
            "projectSummary": "Python SDK",
            "audit": [{"skill": "old-testing", "status": "outdated", "reason": "Retired command"}],
            "recommendations": [
                {"slug": "python-best-practices", "score": 0.97, "reason": "Matches repo"}
            ],
            "gapAnalysis": None,
        },
    )
    result = await _with_sdk(cli, lambda sdk: sdk.get_learning_recommendations(deep=True))
    assert result.recommendations[0].score == 0.97


@pytest.mark.asyncio
async def test_learning_recommendations_reject_malformed_score(tmp_path: Path) -> None:
    """Non-numeric recommendation scores fail result validation."""
    cli = _feature_cli(
        tmp_path,
        method="autohand.learn.recommend",
        params={},
        result={
            "success": True,
            "projectSummary": "SDK",
            "audit": [],
            "recommendations": [{"slug": "testing", "score": "high", "reason": "Useful"}],
            "gapAnalysis": "Needs integration tests",
        },
    )
    with pytest.raises(ValidationError):
        await _with_sdk(cli, lambda sdk: sdk.get_learning_recommendations())
