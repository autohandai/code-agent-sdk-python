"""22 SDLC Release Readiness - ask the agent to run production gates."""
from __future__ import annotations

import asyncio

from _helpers import sdk_config

from autohand_sdk import AutohandSDK


async def main() -> None:
    """Run release readiness checks through the agent."""
    prompt = "\n".join(
        [
            "Run a release-readiness pass for this Python SDK.",
            "Use these gates: uv run pytest, uv run ruff check ., uv run mypy src.",
            "If a command fails, stop and explain the failure with file references.",
            "If all commands pass, summarize residual risks.",
        ]
    )

    tool_results: list[tuple[str, object]] = []

    async with AutohandSDK(
        **sdk_config(permission_mode="default", skill_refs=["testing"])
    ) as sdk:
        async for event in sdk.stream_prompt(prompt):
            if event["type"] == "message_update":
                print(event.get("delta", ""), end="", flush=True)
            elif event["type"] == "tool_start":
                print(f"\n[tool:start] {event.get('tool_name')}")
            elif event["type"] == "tool_update":
                print(event.get("output", ""), end="", flush=True)
            elif event["type"] == "tool_end":
                name = str(event.get("tool_name") or event.get("toolName"))
                success = event.get("success")
                tool_results.append((name, success))
                print(f"\n[tool:end] {name} success={success}")
            elif event["type"] == "permission_request":
                print(f"\n[permission] {event.get('tool')}: {event.get('description')}")
            elif event["type"] == "error":
                print(f"\n[error] {event.get('message')}")

    if tool_results:
        print("\n--- tool summary ---")
        for name, success in tool_results:
            print(f"{name}: {success}")


if __name__ == "__main__":
    asyncio.run(main())
