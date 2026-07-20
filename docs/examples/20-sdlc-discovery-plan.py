"""20 SDLC Discovery Plan - ask for a read-only discovery and plan."""

from __future__ import annotations

import asyncio

from _helpers import print_stream, sdk_config

from autohand_sdk import AutohandSDK


async def main() -> None:
    """Run a discovery-only planning prompt."""
    prompt = "\n".join(
        [
            "Run a discovery pass for this Python SDK.",
            "Do not edit files.",
            "Map the package structure, current test coverage, docs state, and release blockers.",
            "Return a concise implementation plan with priorities.",
        ]
    )

    async with AutohandSDK(**sdk_config(permission_mode="default", skill_refs=["testing"])) as sdk:
        await print_stream(sdk, prompt)


if __name__ == "__main__":
    asyncio.run(main())
