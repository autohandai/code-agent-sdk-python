"""Example: Basic agent interaction.

This example demonstrates the simplest possible usage of the Autohand SDK
to send a prompt and receive a response.
"""
import asyncio

from autohand_sdk import AutohandSDK


async def main() -> None:
    """Run a basic agent interaction."""
    # Create SDK instance with default configuration
    sdk = AutohandSDK(
        cwd=".",
        model="fantail2",
    )

    try:
        # Start the SDK
        await sdk.start()

        # Stream a prompt and handle events
        async for event in sdk.stream_prompt("Write a hello world program in Python"):
            if event["type"] == "agent_start":
                print(f"Agent started: {event['session_id']}")

            elif event["type"] == "message_end":
                print(f"Response: {event.get('content', '')}")

            elif event["type"] == "agent_end":
                print(f"Agent ended: {event['session_id']}")

    except Exception as e:
        print(f"Error: {e}")

    finally:
        # Clean up
        await sdk.stop()


if __name__ == "__main__":
    asyncio.run(main())
