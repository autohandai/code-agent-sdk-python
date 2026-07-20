"""06 Prompt Skills - make named skills available for prompt references."""

from __future__ import annotations

import asyncio

from _helpers import print_stream, sdk_config

from autohand_sdk import AutohandSDK


async def main() -> None:
    """Load skills and reference them from prompt text."""
    config = sdk_config(
        skill_refs=["typescript", "testing", "react"],
    )

    prompt = "Using /skill testing, suggest a focused test plan for this Python SDK."

    async with AutohandSDK(**config) as sdk:
        await print_stream(sdk, prompt)


if __name__ == "__main__":
    asyncio.run(main())
