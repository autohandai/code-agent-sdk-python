"""Example: Skills mentioned in prompt.

This example shows how to configure skills so the agent can reference
them via /skill <name> in prompts. The SDK pre-loads the skills.
"""

import asyncio
import os

from autohand_sdk import AutohandSDK


async def main() -> None:
    """Run an agent with skills referenced in prompt."""
    # Configure available skills
    sdk = AutohandSDK(
        cwd=".",
        provider="autohandai",
        model="fantail",
        api_key=os.environ["AUTOHAND_AI_API_KEY"],
        skills=["typescript", "testing", "react"],
    )

    try:
        await sdk.start()

        # Agent references skills in prompt
        async for event in sdk.stream_prompt(
            "Review this code using /skill typescript best practices"
        ):
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
