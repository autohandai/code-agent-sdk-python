# Error Handling

Errors in the SDK fall into three categories: transport errors, JSON-RPC errors, and agent loop errors.

## Transport Errors

These happen when the CLI subprocess cannot start, crashes, or disconnects.

```python
try:
    await sdk.start()
except Exception as exc:
    print(f"Failed to start CLI: {exc}")
```

Common causes:
- `cli_path` points to a missing binary.
- The CLI config (`~/.autohand/config.json`) has an invalid provider or missing API key.
- The CLI process exited with a non-zero code.

When `startup_check=True` (the default), `start()` probes the CLI with `get_state` after spawning. If the probe fails, the SDK raises a `TransportError` that includes the CLI stderr tail.

## JSON-RPC Errors

These happen when the CLI rejects a request.

```python
from autohand_sdk import RPCError

try:
    state = await sdk.get_state()
except RPCError as exc:
    print(f"RPC error {exc.code}: {exc.data}")
```

Common causes:
- Calling `get_state()` before `start()`.
- Calling `set_model()` with an unsupported model string.
- Calling `respond_to_permission()` with an expired `request_id`.

## Agent Loop Errors

These appear as `error` events in the event stream.

```python
async for event in sdk.stream_prompt("Hello"):
    if event["type"] == "error":
        print(f"Agent error: {event.get('message')}")
```

Common causes:
- The LLM provider returned an HTTP error.
- A tool execution threw an exception.
- The context window exceeded the model limit.

## Timeouts

Set `timeout` in milliseconds when creating the SDK:

```python
sdk = AutohandSDK(
    cwd=".",
    timeout=60000,  # 60 seconds.
)
```

If a request hangs, the SDK raises `RequestTimeoutError`.

## Aborting a Run

If you need to stop the agent mid-turn:

```python
await sdk.abort(reason="User cancelled")
```

## Recovery Patterns

### Restart on Crash

```python
async def resilient_prompt(sdk: AutohandSDK, message: str) -> None:
    try:
        async for event in sdk.stream_prompt(message):
            # Handle events.
            pass
    except Exception:
        print("Stream failed, attempting restart...")
        await sdk.stop()
        await sdk.start()

        async for event in sdk.stream_prompt(message):
            # Retry.
            pass
```

### Graceful Shutdown

Always call `stop()` or use the async context manager before your process exits:

```python
async with AutohandSDK(cwd=".") as sdk:
    async for event in sdk.stream_prompt("Hello"):
        pass
```

## Exception Types

```python
from autohand_sdk import (
    TransportNotStartedError,
    RequestTimeoutError,
    RPCError,
    TransportError,
)
```

| Exception | When it occurs |
|---|---|
| `TransportNotStartedError` | Request attempted before `start()`. |
| `RequestTimeoutError` | No JSON-RPC response before `timeout`. |
| `RPCError` | CLI returned a JSON-RPC error. Has `code` and `data`. |
| `TransportError` | Subprocess failed to start or crashed. |
