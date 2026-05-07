"""05 File Editor - route permissions while asking for a small edit."""
from __future__ import annotations

import asyncio

from _helpers import example_workspace, print_stream, sdk_config

from autohand_sdk import AutohandSDK


async def main() -> None:
    """Create a scratch file and ask the agent to improve it."""
    workspace = example_workspace("file-editor")
    scratch = workspace / "greet.py"
    scratch.write_text(
        "def greet(name):\n"
        "    return 'Hello, ' + name\n",
        encoding="utf-8",
    )

    prompt = (
        f"Edit {scratch.name} to add type hints and a short docstring. "
        "Keep the behavior the same."
    )

    async with AutohandSDK(
        **sdk_config(cwd=str(workspace), permission_mode="default")
    ) as sdk:
        await print_stream(
            sdk,
            prompt,
            auto_allow=False,
            context={"files": [scratch.name]},
        )

    print(f"\nScratch workspace: {workspace}")


if __name__ == "__main__":
    asyncio.run(main())
