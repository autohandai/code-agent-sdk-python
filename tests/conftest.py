"""Pytest configuration and fixtures."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest


@pytest.fixture
def event_loop():
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for testing."""
    return tmp_path


@pytest.fixture
def mock_cli_binary(temp_dir: Path) -> Path:
    """Create a mock CLI binary for testing."""
    cli_path = temp_dir / "mock-autohand"
    cli_path.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "import sys\n"
        "for line in sys.stdin:\n"
        "    req = json.loads(line)\n"
        '    resp = {"jsonrpc": "2.0", "id": req.get("id"), "result": {"success": True}}\n'
        "    print(json.dumps(resp), flush=True)\n"
    )
    cli_path.chmod(0o755)
    return cli_path
