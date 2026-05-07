# Memory

The Autohand CLI has built-in memory tools (`save_memory` and `recall_memory`) that agents can use to persist facts, preferences, or context across conversation turns and across sessions.

## How It Works

When an agent decides to save something, it calls `save_memory` with a key and value. The CLI writes this to a memory file. On subsequent prompts, the CLI loads relevant memory files into the context window so the agent can recall them.

You do not call memory tools directly from the SDK. You prompt the agent, and the agent decides when to save or recall.

## Saving Memory

```python
await sdk.start()

async for event in sdk.stream_prompt(
    "Remember that I prefer TypeScript over JavaScript."
):
    if event["type"] == "tool_start" and event.get("tool_name") == "save_memory":
        print("Agent is saving to memory...")
    if event["type"] == "message_update":
        print(event.get("delta", ""), end="")
```

## Recalling Memory

In a new session, prompt the agent to retrieve stored facts:

```python
sdk2 = AutohandSDK(cwd=".")
await sdk2.start()

async for event in sdk2.stream_prompt(
    "What programming language do I prefer? Check your memory."
):
    if event["type"] == "message_update":
        print(event.get("delta", ""), end="")
```

The agent calls `recall_memory`, the CLI searches the memory store, and the result appears in the context.

## Inspecting Memory in Context

Call `get_state()` to inspect context usage:

```python
state = await sdk.get_state()
print(f"Context percent used: {state.context_percent}%")
print(f"Messages: {state.message_count}")
```

The `GetStateResult` model includes `context_percent` and `message_count`. Memory files count toward the context window limit.

## Memory File Location

Memory files are stored in the CLI workspace under `.autohand/memory/`. You can inspect them directly if needed.

## Limitations

- The agent decides what to save. You cannot force-save from the SDK.
- Memory retrieval depends on the agent calling `recall_memory`. Prompt the agent explicitly if you need it to check memory.
- Memory files count toward the context window limit. Heavy use of memory increases token usage.

## Example

See `examples/` for a complete script that saves a preference in one session and recalls it in another.
