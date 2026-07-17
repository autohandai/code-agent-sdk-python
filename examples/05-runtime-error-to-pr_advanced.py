"""Example: Advanced runtime error to pull request."""
from __future__ import annotations

import asyncio
import json
import os

from autohand_sdk import AutohandSDK


def github_token_env_name() -> str:
    """Return the configured GitHub token environment-variable name."""
    if os.environ.get("GITHUB_TOKEN"):
        return "GITHUB_TOKEN"
    if os.environ.get("GH_TOKEN"):
        return "GH_TOKEN"
    raise RuntimeError("Set GITHUB_TOKEN or GH_TOKEN before running this example.")


def incident_packet() -> dict[str, object]:
    """Build the example incident metadata supplied to the agent."""
    return {
        "id": "INC-2026-05-12-0417",
        "severity": "sev2",
        "service": "checkout-api",
        "error_signature": "RuntimeError: checkout discount failed while replaying coupon idempotency key",
        "user_impact": "Checkout returns HTTP 500 for guest customers using coupon replay from mobile clients.",
        "stack_trace": "\n".join(
            [
                "RuntimeError: checkout discount failed while replaying coupon idempotency key",
                "  File \"src/checkout/discounts.py\", line 42, in calculate_discount",
                "  File \"src/checkout/session.py\", line 88, in create_checkout_session",
            ]
        ),
        "suspected_files": [
            "src/checkout/discounts.py",
            "src/checkout/session.py",
            "tests/checkout/test_session.py",
        ],
        "reproduction_command": "uv run pytest tests/checkout/test_session.py -k guest_coupon_replay",
        "validation_commands": ["uv run pytest", "uv run ruff check .", "uv run mypy src"],
    }


async def main() -> None:
    """Run the advanced runtime-error-to-PR workflow."""
    target_repo = os.environ.get("AUTOHAND_TARGET_REPO", ".")
    token_env_name = github_token_env_name()
    sdk = AutohandSDK(
        cwd=target_repo,
        provider="autohandai",
        model=os.environ.get("AUTOHAND_MODEL", "fantail"),
        api_key=os.environ["AUTOHAND_AI_API_KEY"],
        timeout=600_000,
    )

    prompt = "\n".join(
        [
            "You are a senior QA engineering agent converting this production incident into a repair pull request.",
            f"A GitHub token is available in {token_env_name}. Do not print or commit it.",
            "Run gh auth status or an equivalent non-secret auth check before pushing.",
            f"Use remote {os.environ.get('AUTOHAND_GITHUB_REMOTE', 'origin')} and base branch {os.environ.get('AUTOHAND_GITHUB_BASE_BRANCH', 'main')}.",
            "Create branch autohand/fix-checkout-incident-inc-2026-05-12-0417, commit the fix, push it, and open a PR.",
            "",
            "Incident packet:",
            "```json",
            json.dumps(incident_packet(), indent=2),
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
