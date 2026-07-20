"""21 SDLC Gated Implementation - implement only after explicit permission."""

from __future__ import annotations

import asyncio

from _helpers import example_workspace, print_stream, sdk_config

from autohand_sdk import AutohandSDK


async def main() -> None:
    """Run a gated implementation workflow."""
    workspace = example_workspace("sdlc-gated-implementation")
    docs_dir = workspace / "docs"
    docs_dir.mkdir(exist_ok=True)
    (docs_dir / "README.md").write_text(
        "# Example Docs\n\nThis placeholder intentionally misses setup details.\n",
        encoding="utf-8",
    )

    prompt = "\n".join(
        [
            "Improve the example docs in docs/README.md for one missing setup gap.",
            "Before editing, explain the exact file and change you intend to make.",
            "Wait for permission if the CLI asks.",
            "After editing, run the narrowest relevant validation.",
        ]
    )

    async with AutohandSDK(
        **sdk_config(
            cwd=str(workspace),
            permission_mode="default",
            skill_refs=["testing"],
        )
    ) as sdk:
        await print_stream(sdk, prompt, auto_allow=False)

    print(f"\nScratch workspace: {workspace}")


if __name__ == "__main__":
    asyncio.run(main())
