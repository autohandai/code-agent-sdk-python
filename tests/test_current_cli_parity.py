"""Regression coverage for the ordinary current CLI RPC controls."""

from unittest.mock import AsyncMock, patch

import pytest

from autohand_sdk.rpc_client import RPCClient


@pytest.mark.asyncio
async def test_current_runtime_controls_use_exact_wire_contracts() -> None:
    """Controls preserve false, null and complete MCP configurations."""
    client = RPCClient()
    with patch.object(
        client, "_request", new_callable=AsyncMock, return_value={"success": True}
    ) as request:
        await client.set_browser_capabilities(2, "1.0.0", ["browser_navigate"])
        await client.set_permission_mode("interactive")
        await client.set_max_thinking_tokens(None)
        await client.get_context_usage()
        await client.reload_plugins()
        await client.toggle_mcp_server("files", False)
        await client.reconnect_mcp_server("files")
        await client.set_mcp_servers({"files": {"command": "server", "args": []}})
    assert [(call.args[0], call.args[1]) for call in request.call_args_list] == [
        (
            "autohand.browserCapabilities.set",
            {"protocolVersion": 2, "extensionVersion": "1.0.0", "tools": ["browser_navigate"]},
        ),
        ("autohand.permissionModeSet", {"mode": "interactive"}),
        ("autohand.maxThinkingTokensSet", {"maxThinkingTokens": None}),
        ("autohand.getContextUsage", {}),
        ("autohand.reloadPlugins", {}),
        ("autohand.mcp.toggleServer", {"serverName": "files", "enabled": False}),
        ("autohand.mcp.reconnectServer", {"serverName": "files"}),
        ("autohand.mcp.setServers", {"servers": {"files": {"command": "server", "args": []}}}),
    ]
