"""Example: Direct skill provision.

This example shows how to provide skills directly, including custom skill
files from local paths. The SDK copies the files to ~/.autohand/skills/.
"""

import asyncio
import os

from autohand_sdk import AutohandSDK


async def main() -> None:
    """Run an agent with direct skill provision."""
    # Mix of built-in skills and custom skill files
    sdk = AutohandSDK(
        cwd=".",
        provider="autohandai",
        model="fantail",
        api_key=os.environ["AUTOHAND_AI_API_KEY"],
        skills=[
            "typescript",  # Built-in skill
            "./skills/my-custom/SKILL.md",  # Local skill file
            "../shared-skills/code-review/SKILL.md",  # Relative path
            {"name": "custom-api", "path": "/path/to/SKILL.md"},  # Named skill
        ],
    )

    try:
        await sdk.start()

        # SDK automatically:
        # 1. Copies ./skills/my-custom/SKILL.md to ~/.autohand/skills/my-custom/
        # 2. Copies ../shared-skills/code-review/SKILL.md to ~/.autohand/skills/code-review/
        # 3. Loads 'typescript' from built-in or community
        # 4. Passes all skill names to CLI via --skills flag

        async for event in sdk.stream_prompt("Review this code"):
            if event["type"] == "message_update":
                print(event.get("delta", ""), end="")

            elif event["type"] == "message_end":
                print(f"\n\nFull response:\n{event.get('content', '')}")

            elif event["type"] == "tool_start":
                print(f"\n[Tool: {event.get('tool_name')}]")

    except Exception as e:
        print(f"Error: {e}")

    finally:
        await sdk.stop()


if __name__ == "__main__":
    asyncio.run(main())
