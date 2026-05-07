# Plan Mode

Plan mode restricts the agent to read-only planning tools. It cannot write files, run commands, or make changes. Use it when you want the agent to inspect the codebase and produce a plan before executing anything.

## Enabling Plan Mode

The Python SDK does not expose a dedicated `set_plan_mode` RPC method on the client. Plan mode is controlled through the CLI startup flags or by prompting the agent to stay in read-only mode.

Pass `plan_mode` when creating the SDK:

```python
sdk = AutohandSDK(
    cwd=".",
    plan_mode=True,
)
```

Note: the Python SDK passes plan mode to the CLI via startup flags. The CLI handles the restriction. If the CLI does not support `plan_mode` as a startup flag, you can achieve the same effect by prompting the agent explicitly:

```python
async for event in sdk.stream_prompt(
    "Plan a refactor to split utils.py into smaller modules. Do not make any changes."
):
    if event["type"] == "message_update":
        print(event.get("delta", ""), end="")
```

## Two-Phase Workflow

The typical pattern is:

1. Start a session and prompt the agent to inspect and plan.
2. Stop the SDK.
3. Review the plan outside the agent loop.
4. Re-start and execute.

```python
# Phase 1: Discovery
plan_sdk = AutohandSDK(cwd=".")
await plan_sdk.start()

async for event in plan_sdk.stream_prompt(
    "Plan a refactor to split utils.py into smaller modules. Do not make any changes."
):
    if event["type"] == "message_update":
        print(event.get("delta", ""), end="")

await plan_sdk.stop()

# Human reviews the plan here.

# Phase 2: Execution
exec_sdk = AutohandSDK(
    cwd=".",
    permission_mode="interactive",
)
await exec_sdk.start()

async for event in exec_sdk.stream_prompt("Execute the refactor plan we discussed."):
    # Handle events, including permission requests.
    if event["type"] == "message_update":
        print(event.get("delta", ""), end="")
    elif event["type"] == "permission_request":
        await exec_sdk.respond_to_permission(
            event["request_id"],
            decision="allow",
            allowed=True,
        )
```

## Plan Mode vs Permission Mode

Plan mode is separate from permission mode. Permission mode controls whether the CLI asks before individual tool calls. Plan mode controls which tools are available at all.

```python
# Plan mode + interactive permissions: safe review with human gates.
sdk = AutohandSDK(
    cwd=".",
    plan_mode=True,
    permission_mode="interactive",
)
```

## Legacy Note

`permission_mode="plan"` was accepted in older versions but is deprecated. New code should use explicit read-only prompting or the `plan_mode` config field if the CLI supports it.

## SDLC Integration

Plan mode is the foundation of the SDLC discovery and gated implementation workflows. See `docs/sdlc-workflows.md` and `examples/` for complete patterns.
