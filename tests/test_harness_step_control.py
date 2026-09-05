"""Opt-in real harness proof with local authentication and Autohand AI HTTP mocks."""

from __future__ import annotations

import asyncio
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from autohand_sdk import Agent, is_step_count


async def test_current_harness_stop_resume(tmp_path: Path) -> None:
    """Persist a real read_file result, pause, then include it in the next model request."""
    cli = os.environ.get("AUTOHAND_TEST_CLI_PATH")
    if not cli:
        pytest.skip("set AUTOHAND_TEST_CLI_PATH to run the current harness integration")
    calls: list[dict[str, object]] = []

    class Provider(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *args: object) -> None:
            pass

        def respond(self, value: object) -> None:
            body = json.dumps(value).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path != "/auth/me":
                self.send_error(400)
                return
            self.respond(
                {
                    "authenticated": True,
                    "user": {"id": "fixture", "email": "sdk@example.test", "name": "SDK Fixture"},
                }
            )

        def do_POST(self) -> None:
            if (
                self.path != "/chat/completions"
                or self.headers.get("Authorization") != "Bearer sdk-fixture-key"
            ):
                self.send_error(400)
                return
            calls.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            message: dict[str, object] = {
                "role": "assistant",
                "content": "continued from persisted evidence",
            }
            if len(calls) == 1:
                message["content"] = "Inspect the evidence file."
                message["tool_calls"] = [
                    {
                        "id": "call-read",
                        "type": "function",
                        "function": {
                            "name": "read_file",
                            "arguments": '{"path":"evidence.txt"}',
                        },
                    }
                ]
            self.respond(
                {
                    "id": "fixture",
                    "choices": [{"message": message, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
                }
            )

    server = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    (tmp_path / "evidence.txt").write_text("sdk-parity-evidence")
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "auth": {"token": "sdk-fixture-key"},
                "provider": "autohandai",
                "autohandai": {
                    "model": "fantail",
                    "plan": "cloud",
                    "authMode": "api-key",
                    "contextWindow": 200000,
                },
                "features": {"autohand_inference": True, "automaticSpecialists": False},
                "telemetry": {"enabled": False},
            }
        )
    )
    agent = None
    try:
        agent = await Agent.create(
            cli_path=cli,
            cwd=str(tmp_path),
            provider="autohandai",
            model="fantail",
            api_key="sdk-fixture-key",
            base_url=url,
            bare=True,
            unrestricted=True,
            extra_args=["--config", str(config)],
            env_vars={
                "AUTOHAND_HOME": str(tmp_path / "home"),
                "AUTOHAND_API_KEY": "sdk-fixture-key",
                "AUTOHAND_API_URL": url,
                "AUTOHAND_AUTH_API_URL": url + "/auth",
                "AUTOHAND_SKIP_PING": "1",
                "AUTOHAND_SKIP_UPDATE_CHECK": "1",
                "AUTOHAND_NO_IDLE_LOGOUT": "1",
                "AUTOHAND_DISABLE_AUTO_REPORT": "1",
            },
        )
        result = await asyncio.wait_for(
            agent.run("Read evidence.txt with read_file.", stop_when=is_step_count(1)), 45
        )
        assert result.status == "stopped"
        assert len(result.steps) == len(calls) == 1
        tool_result = result.steps[0].tool_results[0]
        assert tool_result.success and "sdk-parity-evidence" in (tool_result.output or "")
        result = await asyncio.wait_for(agent.run("Continue using the saved tool result."), 45)
        assert result.status == "completed"
        assert len(calls) == 2
        assert "sdk-parity-evidence" in json.dumps(calls[1]["messages"])
    finally:
        if agent is not None:
            await agent.close()
        server.shutdown()
        server.server_close()
        thread.join()
