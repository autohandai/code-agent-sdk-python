"""07 Direct Skills - pass built-in skill names and local SKILL.md files."""

from __future__ import annotations

import asyncio

from _helpers import example_workspace, print_stream, sdk_config

from autohand_sdk import AutohandSDK


async def main() -> None:
    """Create a local skill file and load it through the SDK."""
    workspace = example_workspace("direct-skills")
    readme = workspace / "README.md"
    readme.write_text(
        "# Example Project\n\nA tiny project used by the Autohand SDK examples.\n",
        encoding="utf-8",
    )

    skill_file = workspace / "skills" / "python-sdk-review" / "SKILL.md"
    skill_file.parent.mkdir(parents=True, exist_ok=True)
    skill_file.write_text(
        "---\n"
        "name: python-sdk-review\n"
        "description: Review Python SDK API ergonomics and docs.\n"
        "---\n\n"
        "Focus on async API ergonomics, error handling, and documentation clarity.\n",
        encoding="utf-8",
    )

    config = sdk_config(
        cwd=str(workspace),
        skill_refs=[
            "testing",
            str(skill_file),
            {"name": "explicit-python-sdk-review", "path": str(skill_file)},
        ],
    )

    async with AutohandSDK(**config) as sdk:
        await print_stream(
            sdk,
            "Review this SDK using the available Python SDK review skill.",
            context={"files": [readme.name]},
        )


if __name__ == "__main__":
    asyncio.run(main())
