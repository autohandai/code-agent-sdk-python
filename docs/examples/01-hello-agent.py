"""01 Hello Agent - minimal Autohand SDK usage."""
from __future__ import annotations

import asyncio
import json

from _helpers import print_stream, sdk_config

from autohand_sdk import AutohandSDK


async def main() -> None:
    """Run a single prompt and print the resulting state."""
    async with AutohandSDK(**sdk_config()) as sdk:
        await print_stream(sdk, "Tell me a good joke about code AI agents.")

        state = await sdk.get_state()
        print("\n--- state ---")
        print(json.dumps(state.model_dump(), indent=2))


if __name__ == "__main__":
    asyncio.run(main())
