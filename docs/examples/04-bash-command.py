"""04 Bash Command - observe tool calls that run commands."""

from __future__ import annotations

import asyncio

from _helpers import print_stream, sdk_config

from autohand_sdk import AutohandSDK


async def main() -> None:
    """Ask for directory facts that usually require shell commands."""
    prompt = (
        "Inspect the current directory with safe read-only commands. "
        "Report the top-level files and the total Python source file count."
    )

    async with AutohandSDK(**sdk_config(permission_mode="default")) as sdk:
        await print_stream(sdk, prompt, auto_allow=False)


if __name__ == "__main__":
    asyncio.run(main())
