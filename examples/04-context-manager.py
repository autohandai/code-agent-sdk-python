"""Example: Using async context manager.

This example shows how to use the SDK with an async context manager
for automatic cleanup.
"""

import asyncio
import os

from autohand_sdk import AutohandSDK


async def main() -> None:
    """Run agent with context manager."""
    # SDK automatically starts and stops with context manager
    async with AutohandSDK(
        cwd=".",
        provider="autohandai",
        model="fantail",
        api_key=os.environ["AUTOHAND_AI_API_KEY"],
    ) as sdk:
        async for event in sdk.stream_prompt("Explain async/await in Python"):
            if event["type"] == "message_update":
                print(event.get("delta", ""), end="")

            elif event["type"] == "message_end":
                print("\n\nResponse received!")


if __name__ == "__main__":
    asyncio.run(main())
