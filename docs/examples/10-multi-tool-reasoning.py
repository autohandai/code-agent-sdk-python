"""10 Multi Tool Reasoning - ask for a cross-file codebase summary."""
from __future__ import annotations

import asyncio

from _helpers import print_stream, sdk_config

from autohand_sdk import AutohandSDK


async def main() -> None:
    """Prompt the agent to combine file reads, search, and reasoning."""
    prompt = (
        "Build a concise architecture map of this Python SDK. "
        "Mention the transport, RPC client, public SDK class, and type models. "
        "Call out the most important production risks if you find any."
    )

    async with AutohandSDK(**sdk_config(permission_mode="default")) as sdk:
        await print_stream(sdk, prompt)


if __name__ == "__main__":
    asyncio.run(main())
