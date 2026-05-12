"""26 Advanced Runtime Error to Pull Request.

Build a production incident packet, verify that GitHub credentials are available
through environment variables, and ask Autohand to create a tested repair pull
request.

Required:
    AUTOHAND_TARGET_REPO=/path/to/app
    GITHUB_TOKEN or GH_TOKEN with repo scope
"""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import asdict, dataclass
from typing import Any

from _helpers import sdk_config

from autohand_sdk import AutohandSDK


@dataclass(frozen=True)
class GitHubCredentials:
    token_env_name: str
    remote: str
    base_branch: str
    repository: str | None


@dataclass(frozen=True)
class IncidentPacket:
    id: str
    severity: str
    service: str
    first_seen: str
    release: str
    error_signature: str
    user_impact: str
    stack_trace: str
    logs: list[str]
    request: dict[str, Any]
    suspected_files: list[str]
    reproduction_command: str
    validation_commands: list[str]


def github_credentials_from_env() -> GitHubCredentials:
    """Return GitHub auth metadata without exposing token values."""
    if os.environ.get("GITHUB_TOKEN"):
        token_env_name = "GITHUB_TOKEN"
    elif os.environ.get("GH_TOKEN"):
        token_env_name = "GH_TOKEN"
    else:
        raise RuntimeError("Set GITHUB_TOKEN or GH_TOKEN before running this example.")

    return GitHubCredentials(
        token_env_name=token_env_name,
        remote=os.environ.get("AUTOHAND_GITHUB_REMOTE", "origin"),
        base_branch=os.environ.get("AUTOHAND_GITHUB_BASE_BRANCH", "main"),
        repository=os.environ.get("GITHUB_REPOSITORY"),
    )


def capture_incident_packet() -> IncidentPacket:
    """Capture a realistic incident report from an application error boundary."""
    return IncidentPacket(
        id="INC-2026-05-12-0417",
        severity="sev2",
        service="checkout-api",
        first_seen="2026-05-12T09:14:22Z",
        release="checkout-api@2026.05.12.3",
        error_signature="RuntimeError: checkout discount failed while replaying coupon idempotency key",
        user_impact="Checkout returns HTTP 500 for guest customers using coupon replay from mobile clients.",
        stack_trace="\n".join(
            [
                "RuntimeError: checkout discount failed while replaying coupon idempotency key",
                "  File \"src/checkout/discounts.py\", line 42, in calculate_discount",
                "  File \"src/checkout/payment_intent.py\", line 118, in build_payment_intent",
                "  File \"src/checkout/session.py\", line 88, in create_checkout_session",
            ]
        ),
        logs=[
            "level=error trace=trk_94 request_id=req_7f2 route=POST /checkout status=500 duration_ms=184",
            "level=warn trace=trk_94 idempotency_key=checkout:cart_live_9834:attempt_2 cache_status=miss",
            "level=info trace=trk_94 feature_flags=discount-v2,coupon-replay",
        ],
        request={
            "method": "POST",
            "path": "/checkout",
            "payload": {
                "cart_id": "cart_live_9834",
                "subtotal": 129,
                "customer": None,
                "coupon": {"code": "SPRING25", "source": "mobile-v5"},
                "idempotency_key": "checkout:cart_live_9834:attempt_2",
            },
            "headers": {
                "x-client-version": "ios/5.18.0",
                "x-request-id": "req_7f2",
            },
        },
        suspected_files=[
            "src/checkout/discounts.py",
            "src/checkout/payment_intent.py",
            "src/checkout/session.py",
            "tests/checkout/test_session.py",
        ],
        reproduction_command="uv run pytest tests/checkout/test_session.py -k guest_coupon_replay",
        validation_commands=[
            "uv run pytest tests/checkout/test_session.py -k guest_coupon_replay",
            "uv run pytest",
            "uv run ruff check .",
            "uv run mypy src",
        ],
    )


def build_prompt(incident: IncidentPacket, github: GitHubCredentials) -> str:
    repo_hint = (
        f"- GitHub repository hint: {github.repository}."
        if github.repository
        else "- Discover the GitHub repository from git remote output."
    )
    return "\n".join(
        [
            "You are a senior QA engineering agent responsible for converting production incidents into verified repair pull requests.",
            "",
            "GitHub credentials:",
            f"- A GitHub token is available in the {github.token_env_name} environment variable. Do not print or commit the token.",
            f"- Use git remote {github.remote}.",
            f"- Open the pull request against {github.base_branch}.",
            repo_hint,
            "- Before pushing, run gh auth status or an equivalent non-secret auth check.",
            "",
            "Incident packet:",
            "```json",
            json.dumps(asdict(incident), indent=2),
            "```",
            "",
            "Required workflow:",
            "1. Inspect the target repository and confirm the likely failing path.",
            "2. Reproduce the incident using the provided payload or nearest existing test harness.",
            "3. Fix the root cause, not just the thrown exception.",
            "4. Add a regression test covering guest checkout, coupon replay, and idempotency behavior.",
            "5. Run the focused test first, then the relevant validation commands.",
            "6. Create a branch named autohand/fix-checkout-incident-inc-2026-05-12-0417.",
            "7. Commit the fix with a clear message.",
            "8. Push the branch and open a pull request.",
            "9. In the PR body, include the incident id, error signature, files changed, tests run, and any residual risk.",
        ]
    )


async def main() -> None:
    target_repo = os.environ.get("AUTOHAND_TARGET_REPO", ".")
    github = github_credentials_from_env()
    prompt = build_prompt(capture_incident_packet(), github)

    async with AutohandSDK(
        **sdk_config(
            cwd=target_repo,
            permission_mode="default",
            skill_refs=["testing"],
            timeout=600_000,
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
