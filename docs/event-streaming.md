# Event Streaming

`stream_prompt()` returns an async generator that yields event dictionaries as they happen. You read them in an `async for` loop and decide what to show the user.

## Basic Pattern

```python
async for event in sdk.stream_prompt("Hello"):
    if event["type"] == "message_update":
        print(event.get("delta", ""), end="")
```

## Event Types

### message_update

A chunk of the agent response. Concatenate `delta` to build the full message.

```python
if event["type"] == "message_update":
    print(event.get("delta", ""), end="")
```

### message_end

The agent finished generating. `content` contains the full message string.

```python
if event["type"] == "message_end":
    print("\n--- done ---")
```

### tool_start

The agent called a tool.

```python
if event["type"] == "tool_start":
    print(f"[tool: {event.get('tool_name')}]")
```

### tool_update

Streaming output from a running tool (stdout or file contents).

```python
if event["type"] == "tool_update":
    print(event.get("output", ""), end="")
```

### tool_end

The tool finished. `result` may contain the final output.

```python
if event["type"] == "tool_end":
    print(f"[tool completed: {event.get('tool_name')}]")
    if event.get("result"):
        print(str(event["result"])[:500])
```

### permission_request

The CLI needs approval before running a tool.

```python
if event["type"] == "permission_request":
    print(f"Permission needed: {event.get('tool')}")
    print(f"Description: {event.get('description')}")

    await sdk.respond_to_permission(
        event["request_id"],
        decision="allow",
        allowed=True,
    )
```

### error

Something went wrong inside the agent loop or transport.

```python
if event["type"] == "error":
    print("Agent error:", event.get("message"))
```

## Building a Simple Chat UI

```python
full_message = ""

async for event in sdk.stream_prompt(user_input):
    if event["type"] == "message_update":
        print(event.get("delta", ""), end="")
        full_message += event.get("delta", "")

    elif event["type"] == "tool_start":
        print(f"\n[running {event.get('tool_name')}]")

    elif event["type"] == "tool_end":
        print(f"[{event.get('tool_name')} done]")

    elif event["type"] == "permission_request":
        is_shell = event.get("tool") in ("bash", "run_command")
        await sdk.respond_to_permission(
            event["request_id"],
            decision="allow" if not is_shell else "deny",
            allowed=not is_shell,
        )

    elif event["type"] == "error":
        print("Error:", event.get("message"))
```

## Typed Event Parsing

The SDK can parse raw event dictionaries into Pydantic models:

```python
from autohand_sdk import parse_sdk_event

async for raw_event in sdk.stream_prompt("Hello"):
    event = parse_sdk_event(raw_event)
    if not isinstance(event, dict) and event.type == "message_update":
        print(event.delta or "", end="")
```

Unknown event types are returned unchanged as dictionaries, so you do not lose access to new CLI notifications.

## Subscribing to All Events

If you want events outside of a prompt stream:

```python
async for event in sdk.events():
    print(event["type"])
```

This includes lifecycle events like `agent_start` and `agent_end`.
