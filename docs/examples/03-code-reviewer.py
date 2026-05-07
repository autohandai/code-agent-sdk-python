"""03 Code Reviewer - ask the agent to inspect project files."""
from __future__ import annotations

import asyncio

from _helpers import print_stream, sdk_config

from autohand_sdk import AutohandSDK


async def main() -> None:
    """Run a file-aware review prompt."""
    prompt = (
        "Review the Python SDK files for production risks. "
        "Focus on correctness, API clarity, and missing tests."
    )
    context = {
        "files": [
            "src/autohand_sdk/sdk.py",
            "src/autohand_sdk/rpc_client.py",
            "src/autohand_sdk/transport.py",
        ]
    }

    async with AutohandSDK(**sdk_config()) as sdk:
        await print_stream(sdk, prompt, context=context)


if __name__ == "__main__":
    asyncio.run(main())
