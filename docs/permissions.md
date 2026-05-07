# Permissions

The Autohand CLI asks before executing shell commands, file writes, and other destructive tools. The SDK surfaces these requests as events and lets you respond programmatically.

## Permission Modes

Set the mode when creating the SDK instance:

```python
sdk = AutohandSDK(
    cwd=".",
    permission_mode="interactive",  # Ask every time (default)
)
```

| Mode | Behavior |
|---|---|
| `interactive` | Emit `permission_request` events. Your code decides. |
| `unrestricted` | Allow everything without asking. |
| `restricted` | Deny risky tools automatically. |
| `external` | Delegate decisions to a configured callback. |

Legacy aliases like `default` and `bypassPermissions` still work but should not be used in new code.

## Responding to Permission Requests

During `stream_prompt()`, watch for `permission_request` events:

```python
async for event in sdk.stream_prompt("Run tests"):
    if event["type"] == "permission_request":
        print(f"Tool: {event.get('tool')}")
        print(f"Description: {event.get('description')}")

        await sdk.respond_to_permission(
            event["request_id"],
            decision="allow",
            allowed=True,
        )
```

## Granular Control

Use `PermissionSettings` for fine-grained rules:

```python
from autohand_sdk import PermissionSettings

sdk = AutohandSDK(
    cwd=".",
    permissions=PermissionSettings(
        mode="interactive",
        allow_list=["read_file", "write_file", "git_status"],
        deny_list=["delete_path", "run_command"],
    ),
)
```

Tools matching `allow_list` pass through. Tools matching `deny_list` are blocked.

## Yolo Patterns

For unattended scripts, auto-approve tools matching a pattern:

```python
sdk = AutohandSDK(
    cwd=".",
    yolo="allow:read,write",
    yolo_timeout=60,  # Auto-approve expires after 60 seconds.
)
```

## Changing Mode at Runtime

The Python SDK does not expose a dedicated `set_permission_mode` RPC method on the client. You can restart the SDK with new settings, or use the `permissions` config at initialization time.

## Permission Decision Scopes

When responding, you can scope the decision:

```python
await sdk.respond_to_permission(
    event["request_id"],
    decision="allow",
    allowed=True,
    remember=True,   # Remember this decision for the session.
)
```

Set `remember=False` to ask again next time the same tool is called.

## Complete Example

```python
async for event in sdk.stream_prompt("Refactor the codebase"):
    if event["type"] == "message_update":
        print(event.get("delta", ""), end="")

    elif event["type"] == "permission_request":
        tool = event.get("tool", "")
        description = event.get("description", "")

        # Auto-allow safe reads, ask for writes and commands
        allowed = tool in ("read_file", "list_dir", "grep_search")

        print(f"\n[Permission: {tool}] {description}")
        print(f"Decision: {'allow' if allowed else 'deny'}")

        await sdk.respond_to_permission(
            event["request_id"],
            decision="allow" if allowed else "deny",
            allowed=allowed,
        )
```
