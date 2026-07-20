"""02 Streaming Query - handle each event type explicitly."""

from __future__ import annotations

import asyncio
import sys

from _helpers import sdk_config

from autohand_sdk import AutohandSDK


def handle_event(event: dict[str, object]) -> None:
    """Print useful information for a stream event."""
    event_type = event["type"]

    if event_type == "agent_start":
        print(f"\n[agent:start] {event.get('session_id')}")
        print(f"model={event.get('model')}")
    elif event_type == "turn_start":
        print(f"\n[turn:start] {event.get('turn_id')}")
    elif event_type == "message_start":
        print(f"\n[message:start] {event.get('message_id')}")
    elif event_type == "message_update":
        print(str(event.get("delta", "")), end="", flush=True)
    elif event_type == "message_end":
        print("\n[message:end]")
    elif event_type == "tool_start":
        print(f"\n[tool:start] {event.get('tool_name')}")
    elif event_type == "tool_update":
        print(str(event.get("output", "")), end="", flush=True)
    elif event_type == "tool_end":
        print(f"\n[tool:end] {event.get('tool_name')} success={event.get('success')}")
    elif event_type == "permission_request":
        print(f"\n[permission] {event.get('tool')}: {event.get('description')}")
    elif event_type == "agent_end":
        print(f"\n[agent:end] {event.get('reason')}")
    elif event_type == "error":
        print(f"\n[error] {event.get('message')}", file=sys.stderr)


async def main() -> None:
    """Stream one prompt and display structured events."""
    async with AutohandSDK(**sdk_config()) as sdk:
        async for event in sdk.stream_prompt("Explain closures in one sentence."):
            handle_event(event)


if __name__ == "__main__":
    asyncio.run(main())
