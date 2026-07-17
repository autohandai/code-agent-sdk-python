"""Example: Runtime error to pull request.

This variant uses the package-level example style. For the full documented
version, see docs/examples/26-runtime-error-to-pr.py.
"""
from __future__ import annotations

import asyncio
import os
import traceback

from autohand_sdk import AutohandSDK


def checkout_discount(cart: dict[str, object]) -> float:
    """Reproduce a checkout discount calculation from an incident."""
    try:
        customer = cart["customer"]
        loyalty_tier = customer["loyalty_tier"]  # type: ignore[index]
        return float(cart["subtotal"]) * (0.15 if loyalty_tier == "gold" else 0.05)
    except Exception as exc:
        raise RuntimeError(f"checkout discount failed: {exc}") from exc


def capture_runtime_error() -> str:
    """Capture the representative runtime failure as a traceback."""
    try:
        checkout_discount({"subtotal": 129, "customer": None})
    except Exception:
        return traceback.format_exc()
    return "RuntimeError: checkout discount failed when customer was null"


async def main() -> None:
    """Ask the agent to reproduce, repair, test, commit, and open a PR."""
    target_repo = os.environ.get("AUTOHAND_TARGET_REPO", ".")
    sdk = AutohandSDK(
        cwd=target_repo,
        provider="autohandai",
        model=os.environ.get("AUTOHAND_MODEL", "fantail"),
        api_key=os.environ["AUTOHAND_AI_API_KEY"],
        timeout=300_000,
    )

    prompt = "\n".join(
        [
            "You are a QA engineering agent that turns production error reports into small repair pull requests.",
            "Fix the root cause, add or update a focused regression test, run validation, commit the fix, push a branch, and create a pull request.",
            "",
            "Captured error:",
            "```text",
            capture_runtime_error(),
            "```",
        ]
    )

    try:
        await sdk.start()
        async for event in sdk.stream_prompt(prompt):
            if event["type"] == "message_update":
                print(event.get("delta", ""), end="", flush=True)
            elif event["type"] == "tool_start":
                print(f"\n[tool] {event.get('tool_name')}")
            elif event["type"] == "error":
                print(f"\n[error] {event.get('message')}")
    finally:
        await sdk.stop()


if __name__ == "__main__":
    asyncio.run(main())
