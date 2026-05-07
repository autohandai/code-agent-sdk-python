# Migrating from the Library SDK

The previous Python SDK was a direct library with in-process LLM provider integration. This SDK is a CLI wrapper that spawns the Autohand CLI as a subprocess and communicates over JSON-RPC.

## Key Differences

| Library SDK | CLI Wrapper SDK |
|---|---|
| Direct provider calls in-process. | Delegates to CLI subprocess. |
| Import providers individually. | Configure provider in `~/.autohand/config.json`. |
| `agent.run()` returns a string. | `stream_prompt()` yields events; collect text yourself. |
| Built-in tool system. | Tools run inside the CLI; you observe via events. |

## Replacing Agent.run()

Old:

```python
from autohand_sdk import Agent

agent = Agent(provider=openrouter, tools=[...])
result = await agent.run("Summarize the API")
print(result)
```

New:

```python
from autohand_sdk import AutohandSDK

sdk = AutohandSDK(cwd=".")
await sdk.start()

text = ""
async for event in sdk.stream_prompt("Summarize the API"):
    if event["type"] == "message_update":
        text += event.get("delta", "")
        print(event.get("delta", ""), end="")

await sdk.stop()
print(text)
```

Or use the context manager for automatic cleanup:

```python
async with AutohandSDK(cwd=".") as sdk:
    async for event in sdk.stream_prompt("Summarize the API"):
        if event["type"] == "message_update":
            print(event.get("delta", ""), end="")
```

## Replacing Provider Configuration

Old:

```python
from autohand_sdk.providers import OpenRouterProvider

provider = OpenRouterProvider(api_key="sk-or-...")
```

New:

Create `~/.autohand/config.json`:

```json
{
  "provider": "openrouter",
  "openrouter": {
    "apiKey": "sk-or-...",
    "model": "openrouter/auto"
  }
}
```

The SDK and CLI read this file automatically. Or pass inline:

```python
sdk = AutohandSDK(
    cwd=".",
    provider="openrouter",
    api_key="sk-or-...",
)
```

## Replacing Tool Registration

Old:

```python
agent.register_tool(
    name="read_file",
    execute=lambda path: open(path).read(),
)
```

New:

The CLI has built-in tools. You do not register them from the SDK. You observe tool calls via events:

```python
async for event in sdk.stream_prompt("Read README.md"):
    if event["type"] == "tool_start":
        print(f"Tool called: {event.get('tool_name')}")
```

## Replacing Streaming

Old:

```python
async for token in agent.stream("Hello"):
    print(token, end="")
```

New:

```python
async for event in sdk.stream_prompt("Hello"):
    if event["type"] == "message_update":
        print(event.get("delta", ""), end="")
```

The new API yields structured event dictionaries, not raw tokens. You handle `message_update`, `tool_start`, `tool_end`, and `permission_request` yourself.

## Replacing Memory

Old:

```python
agent.memory.save("preference", "typescript")
value = agent.memory.recall("preference")
```

New:

Memory is managed by the CLI. Prompt the agent to save or recall:

```python
async for event in sdk.stream_prompt("Remember that I prefer TypeScript."):
    pass

async for event in sdk.stream_prompt("What language do I prefer? Check memory."):
    pass
```

## Package Name Change

The Python package is `autohand-sdk`:

```bash
pip install autohand-sdk
```

Or with uv:

```bash
uv add autohand-sdk
```

## When to Stay on the Library SDK

- You need in-process provider control for custom retries or caching.
- You want to avoid the CLI binary overhead.
- You run in an environment where spawning subprocesses is restricted.

For all other cases, the CLI wrapper gives you the full feature set of the CLI with zero drift between CLI and SDK behavior.
