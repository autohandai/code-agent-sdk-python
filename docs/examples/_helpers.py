"""Shared helpers for Autohand SDK examples."""
from __future__ import annotations

import os
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from tempfile import gettempdir
from typing import Any

from autohand_sdk import AutohandSDK, RequestTimeoutError, RPCError, TransportNotStartedError


def sdk_config(**overrides: Any) -> dict[str, Any]:
    """Return common SDK configuration for examples."""
    config: dict[str, Any] = {
        "cwd": str(Path.cwd()),
        "debug": os.environ.get("AUTOHAND_DEBUG") == "1",
    }

    model = os.environ.get("AUTOHAND_MODEL")
    if model:
        config["model"] = model

    cli_path = os.environ.get("AUTOHAND_CLI_PATH")
    if cli_path:
        config["cli_path"] = cli_path

    config.update({key: value for key, value in overrides.items() if value is not None})
    return config


def example_workspace(name: str) -> Path:
    """Return an isolated scratch workspace for examples that may write files."""
    slug = "".join(char if char.isalnum() or char in ("-", "_") else "-" for char in name)
    workspace = Path(gettempdir()) / "autohand-sdk-examples" / slug
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


async def print_stream(
    sdk: AutohandSDK,
    message: str,
    *,
    auto_allow: bool = False,
    **prompt_kwargs: Any,
) -> list[dict[str, Any]]:
    """Send a prompt and print useful streaming events."""
    events: list[dict[str, Any]] = []

    async for event in sdk.stream_prompt(message, **prompt_kwargs):
        events.append(event)
        event_type = event["type"]

        if event_type == "message_update":
            print(event.get("delta", ""), end="", flush=True)
        elif event_type == "tool_start":
            print(f"\n[tool:start] {event.get('tool_name') or event.get('toolName')}")
        elif event_type == "tool_update":
            print(event.get("output", ""), end="", flush=True)
        elif event_type == "tool_end":
            tool_name = event.get("tool_name") or event.get("toolName")
            success = event.get("success")
            print(f"\n[tool:end] {tool_name} success={success}")
        elif event_type == "permission_request":
            print(f"\n[permission] {event.get('tool')}: {event.get('description')}")
            if auto_allow:
                request_id = event.get("request_id") or event.get("requestId")
                if request_id:
                    await sdk.respond_to_permission(
                        str(request_id),
                        decision="allow",
                        allowed=True,
                    )
        elif event_type == "error":
            print(f"\n[error] {event.get('message')}", file=sys.stderr)

    print()
    return events


async def run_with_sdk(
    message: str,
    *,
    auto_allow: bool = False,
    config: dict[str, Any] | None = None,
    **prompt_kwargs: Any,
) -> list[dict[str, Any]]:
    """Run one prompt in an SDK context."""
    try:
        async with AutohandSDK(**(config or sdk_config())) as sdk:
            return await print_stream(
                sdk,
                message,
                auto_allow=auto_allow,
                **prompt_kwargs,
            )
    except TransportNotStartedError as exc:
        print(f"Transport not started: {exc}", file=sys.stderr)
    except RequestTimeoutError as exc:
        print(f"Request timed out: {exc}", file=sys.stderr)
    except RPCError as exc:
        print(f"RPC error: {exc} code={exc.code} data={exc.data}", file=sys.stderr)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
    return []


async def collect_content(events: AsyncIterator[dict[str, Any]]) -> str:
    """Collect streamed assistant text from an event iterator."""
    chunks: list[str] = []
    async for event in events:
        if event["type"] == "message_update":
            chunks.append(str(event.get("delta", "")))
        elif event["type"] == "message_end" and event.get("content"):
            return str(event["content"])
    return "".join(chunks)
