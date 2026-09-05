"""CLI startup failures use a null request ID before normal RPC dispatch exists."""

import sys
from pathlib import Path

import pytest

from autohand_sdk import AutohandSDK
from autohand_sdk.errors import TransportError


async def test_null_id_startup_error_preserves_diagnostic(tmp_path: Path) -> None:
    """Expose the startup diagnostic instead of a generic EOF or request timeout."""
    cli = tmp_path / "startup-error"
    cli.write_text(
        f"#!{sys.executable}\n"
        + """\
import json
print(json.dumps({"jsonrpc":"2.0", "id":None, "error":{
    "code": -32000, "message": "fixture authentication is unavailable"
}}), flush=True)
"""
    )
    cli.chmod(0o755)
    sdk = AutohandSDK(cli_path=str(cli), cwd=str(tmp_path))
    with pytest.raises(TransportError, match="fixture authentication is unavailable"):
        await sdk.start()
    await sdk.close()
