# Advanced Patterns

## Custom System Prompts

Replace the entire CLI system prompt before the session starts:

```python
sdk = AutohandSDK(
    cwd=".",
    sys_prompt="./SYSTEM_PROMPT.md",
)
```

Or append to the default prompt:

```python
sdk = AutohandSDK(
    cwd=".",
    append_sys_prompt="Always run type checks before declaring a task done.",
)
```

Both accept file paths or inline strings.

## Context Compaction

When the context window fills up, the CLI can compact older messages into a summary:

```python
from autohand_sdk import ContextSettings

sdk = AutohandSDK(
    cwd=".",
    context=ContextSettings(
        context_compact=True,
        max_tokens=128000,
        compression_threshold=0.7,
        summarization_threshold=0.9,
    ),
)
```

- `compression_threshold`: fraction of context used before summarization starts.
- `summarization_threshold`: fraction at which aggressive compaction kicks in.

## Session Persistence

Save and resume sessions across process restarts:

```python
from autohand_sdk import SessionSettings

sdk = AutohandSDK(
    cwd=".",
    session=SessionSettings(
        persist_session=True,
        session_path="./.autohand/sessions",
        auto_save_interval=60,
    ),
)

await sdk.start()
# ... work ...
state = await sdk.save_session()
```

Note: `save_session()` is a compatibility method. The current CLI does not expose a dedicated save-session RPC method, so it returns current state. Use session startup flags such as `persist_session=True` for CLI-managed persistence.

## Model Switching

Change the model mid-session:

```python
await sdk.set_model("openrouter/auto")
```

This calls `autohand.modelSet` over RPC. Subsequent prompts use the new model.

## Temperature Control

Adjust sampling temperature at runtime:

```python
await sdk.set_temperature(0.2)
```

## Skills API

The SDK supports three ways to provide skills:

### Built-in skills by name

```python
sdk = AutohandSDK(
    cwd=".",
    skill_refs=["typescript", "testing", "react"],
)
```

### Local skill files

```python
sdk = AutohandSDK(
    cwd=".",
    skill_refs=[
        "typescript",
        "./skills/my-custom/SKILL.md",
        "../shared-skills/code-review/SKILL.md",
    ],
)
```

The SDK copies local files to `~/.autohand/skills/<skill-name>/SKILL.md` before starting the CLI.

### Named skill objects

```python
sdk = AutohandSDK(
    cwd=".",
    skill_refs=[
        {"name": "custom-api", "path": "/path/to/SKILL.md"},
    ],
)
```

Disable file copying when you only want to activate already installed skills:

```python
sdk = AutohandSDK(
    cwd=".",
    skill_refs=["testing"],
    copy_skill_files=False,
)
```

## Environment Variables

Forward `AUTOHAND_` variables to the CLI subprocess:

```python
from autohand_sdk import AutohandEnvVars

sdk = AutohandSDK(
    cwd=".",
    env_vars=AutohandEnvVars(
        AUTOHAND_NO_BANNER="1",
        AUTOHAND_DEBUG="1",
        AUTOHAND_STREAM_TOOL_OUTPUT="1",
    ),
)
```

Or pass a plain dict:

```python
sdk = AutohandSDK(
    cwd=".",
    env_vars={"AUTOHAND_NO_BANNER": "1"},
)
```

## Inspecting State

Get the current agent state:

```python
state = await sdk.get_state()
print(state.status)  # 'idle' | 'processing' | 'waiting_permission'
```

Get recent messages:

```python
messages = await sdk.get_messages(limit=10)
```

Get account information:

```python
account = await sdk.get_account_info()
```

## Combining Patterns

A complete integration might look like this:

```python
from autohand_sdk import AutohandSDK, ContextSettings, SessionSettings

async with AutohandSDK(
    cwd=".",
    model="openrouter/auto",
    temperature=0.7,
    debug=True,
    auto_mode=True,
    max_iterations=10,
    permission_mode="interactive",
    skill_refs=["typescript"],
    context=ContextSettings(
        context_compact=True,
        max_tokens=128000,
    ),
    session=SessionSettings(
        persist_session=True,
        session_path="./.autohand/sessions",
    ),
    append_sys_prompt="Write tests for every new module.",
) as sdk:

    async for event in sdk.stream_prompt("Plan the refactor"):
        if event["type"] == "message_update":
            print(event.get("delta", ""), end="")

    # Review plan, then execute
    async for event in sdk.stream_prompt("Implement the plan"):
        if event["type"] == "message_update":
            print(event.get("delta", ""), end="")
        elif event["type"] == "permission_request":
            await sdk.respond_to_permission(
                event["request_id"],
                decision="allow",
                allowed=True,
            )
```
