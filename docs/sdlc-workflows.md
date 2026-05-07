# SDLC Workflows With The Python SDK

These workflows use the Python SDK as an async orchestration layer around the
Autohand CLI. They mirror the TypeScript and Go SDK examples while using
`asyncio`, `async with`, and `async for` event streams.

## Discovery And Planning

Use plan mode when the task is still ambiguous:

```python
from autohand_sdk import AutohandSDK

async with AutohandSDK(
    cwd=".",
    plan_mode=True,
    append_sys_prompt="Inspect first. Produce a concrete plan before implementation.",
) as sdk:
    async for event in sdk.stream_prompt(
        "Plan the smallest safe implementation for this feature. Do not edit files."
    ):
        if event["type"] == "message_update":
            print(event.get("delta", ""), end="", flush=True)
```

See `docs/examples/20-sdlc-discovery-plan.py`.

## Gated Implementation

Run a read-only pass, review the plan in your host application, then execute only
after an explicit gate:

```python
from autohand_sdk import AutohandSDK


async def collect_text(sdk: AutohandSDK, prompt: str) -> str:
    text = ""
    async for event in sdk.stream_prompt(prompt):
        if event["type"] == "message_update":
            delta = event.get("delta", "")
            text += delta
            print(delta, end="", flush=True)
    return text


async with AutohandSDK(cwd=".", plan_mode=True) as plan_sdk:
    plan = await collect_text(plan_sdk, "Plan this change without editing files.")

if not approved_by_host(plan):
    raise SystemExit("plan was not approved")

async with AutohandSDK(cwd=".", permission_mode="interactive") as exec_sdk:
    async for event in exec_sdk.stream_prompt("Implement the approved plan."):
        if event["type"] == "message_update":
            print(event.get("delta", ""), end="", flush=True)
        elif event["type"] == "permission_request":
            await exec_sdk.respond_to_permission(
                event["request_id"],
                decision="allow",
                allowed=True,
            )
```

See `docs/examples/21-sdlc-gated-implementation.py`.

## Release Readiness

Ask the agent to run the checks that matter for the repository and stream
progress back to the host:

```python
async with AutohandSDK(
    cwd=".",
    append_sys_prompt="Report commands run, failures, and residual release risk.",
) as sdk:
    async for event in sdk.stream_prompt(
        """Run release readiness:
- uv run ruff check .
- uv run mypy src
- uv run pytest
- inspect README and examples for API drift
"""
    ):
        if event["type"] == "tool_start":
            print(f"\n[tool: {event.get('tool_name')}]")
        elif event["type"] == "message_update":
            print(event.get("delta", ""), end="", flush=True)
```

See `docs/examples/22-sdlc-release-readiness.py`.

## Structured Review Output

Use JSON output when another system will consume the result. The Python SDK does
not force provider-level constrained decoding; prompt for JSON and validate the
parsed result in your host code.

```python
import json
from pydantic import BaseModel


class ReleaseRisk(BaseModel):
    summary: str
    risks: list[str]


async with AutohandSDK(cwd=".") as sdk:
    text = ""
    async for event in sdk.stream_prompt(
        "Return JSON with keys summary and risks for this release."
    ):
        if event["type"] == "message_update":
            text += event.get("delta", "")

risk = ReleaseRisk.model_validate(json.loads(text))
print(risk.summary)
```

For a fuller event-driven workflow, see the examples directory.
