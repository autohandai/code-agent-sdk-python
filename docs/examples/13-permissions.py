"""13 Permissions - respond to permission requests from Python."""
from __future__ import annotations

import asyncio

from _helpers import example_workspace, sdk_config

from autohand_sdk import AutohandSDK


async def main() -> None:
    """Demonstrate a host-controlled permission response."""
    workspace = example_workspace("permissions")

    async with AutohandSDK(
        **sdk_config(cwd=str(workspace), permission_mode="default")
    ) as sdk:
        async for event in sdk.stream_prompt(
            "Create a file named permission_example.txt with one sentence."
        ):
            if event["type"] == "permission_request":
                print(f"[permission] {event.get('tool')}: {event.get('description')}")
                request_id = event.get("request_id") or event.get("requestId")
                if request_id:
                    await sdk.respond_to_permission(
                        str(request_id),
                        decision="allow",
                        allowed=True,
                        remember=False,
                    )
            elif event["type"] == "message_update":
                print(event.get("delta", ""), end="", flush=True)
            elif event["type"] == "tool_start":
                print(f"\n[tool:start] {event.get('tool_name')}")
            elif event["type"] == "tool_end":
                print(f"\n[tool:end] {event.get('tool_name')}")

    print(f"\nScratch workspace: {workspace}")


if __name__ == "__main__":
    asyncio.run(main())
