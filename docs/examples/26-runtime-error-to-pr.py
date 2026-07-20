"""26 Runtime Error to Pull Request.

Capture an application runtime error and ask Autohand to turn it into a focused
repair pull request. Set AUTOHAND_TARGET_REPO to the app repository that should
receive the branch, commit, push, and pull request.
"""

from __future__ import annotations

import asyncio
import os
import traceback

from _helpers import sdk_config

from autohand_sdk import AutohandSDK


def checkout_discount(cart: dict[str, object]) -> float:
    """Buggy application function used to simulate a captured runtime error."""
    try:
        customer = cart["customer"]
        loyalty_tier = customer["loyalty_tier"]  # type: ignore[index]
        return float(cart["subtotal"]) * (0.15 if loyalty_tier == "gold" else 0.05)
    except Exception as exc:
        raise RuntimeError(f"checkout discount failed: {exc}") from exc


def capture_runtime_error() -> str:
    """Return the kind of payload an error boundary or logger might capture."""
    try:
        checkout_discount({"subtotal": 129, "customer": None})
    except Exception:
        return traceback.format_exc()

    return "\n".join(
        [
            "RuntimeError: checkout discount failed: 'NoneType' object is not subscriptable",
            '  File "src/checkout/discounts.py", line 42, in checkout_discount',
            '  File "src/checkout/session.py", line 88, in create_checkout_session',
            "Request: POST /checkout",
            'Payload: {"subtotal": 129, "customer": null}',
        ]
    )


async def main() -> None:
    """Ask Autohand to repair the captured runtime failure and create a PR."""
    target_repo = os.environ.get("AUTOHAND_TARGET_REPO", ".")
    captured_error = capture_runtime_error()

    prompt = "\n".join(
        [
            "You are a QA engineering agent that turns production error reports into small repair pull requests.",
            "Reproduce the failure when the repository makes that possible.",
            "Fix the root cause, add or update a focused regression test, run the relevant validation command, commit the fix, push a branch, and create a pull request.",
            "Keep the pull request description concise and include the error signature, the fix summary, and the validation result.",
            "",
            "A runtime error was captured by the application error boundary.",
            "",
            "Captured error:",
            "```text",
            captured_error,
            "```",
            "",
            "Expected user impact:",
            "A checkout session should still calculate a safe default discount when the customer object is missing.",
            "",
            "Please create a pull request with the fix.",
        ]
    )

    async with AutohandSDK(
        **sdk_config(
            cwd=target_repo,
            permission_mode="default",
            skill_refs=["testing"],
            timeout=300_000,
        )
    ) as sdk:
        async for event in sdk.stream_prompt(prompt):
            if event["type"] == "message_update":
                print(event.get("delta", ""), end="", flush=True)
            elif event["type"] == "tool_start":
                print(f"\n[tool] {event.get('tool_name')}")
            elif event["type"] == "permission_request":
                print(f"\n[permission] {event.get('tool')}: {event.get('description')}")
            elif event["type"] == "error":
                print(f"\n[error] {event.get('message')}")


if __name__ == "__main__":
    asyncio.run(main())
