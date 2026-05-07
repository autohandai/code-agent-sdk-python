# Code Agent SDK for Python

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Type Checker: mypy](https://img.shields.io/badge/type%20checker-mypy-blue.svg)](https://mypy-lang.org/)

A production-grade Python SDK for the Autohand CLI, enabling programmatic control of code agents through a high-level async API over the CLI's JSON-RPC mode.

**Beta:** this SDK is actively evolving while the Agent SDK APIs stabilize. Pin versions in production and review release notes before upgrading.

## Other Programming Languages (Beta)

The Agent SDK is available in multiple beta language packages. Use the same CLI-backed SDK model from another programming language:

- [TypeScript](https://github.com/autohandai/code-agent-sdk-typescript) - `Agent`, `Run`, streaming, and JSON helpers for Node and Bun hosts.
- [Go](https://github.com/autohandai/code-agent-sdk-go) - idiomatic Go package with `context.Context`, typed events, and channel-based streaming.
- [Python](https://github.com/autohandai/code-agent-sdk-python) - this package, with `asyncio`, `async for` event streams, and typed Pydantic models.
- [Java](https://github.com/autohandai/code-agent-sdk-java) - Java 21 records, sealed events, and virtual-thread-ready APIs.
- [Swift](https://github.com/autohandai/code-agent-sdk-swift) - SwiftPM package with `Agent`, `Runner`, async streams, tools, hooks, and permissions.

## Features

- **Async/await native** - First-class support for async programming
- **Type-safe** - Full type hints with Pydantic models
- **Skill support** - Configure skills by name or file path
- **Event streaming** - Real-time JSON-RPC notifications from the agent
- **Typed event parsing** - Optional Pydantic parsing for known event types
- **Automatic cleanup** - Context manager support for resource management
- **Production transport** - Response matching, notification routing, timeouts, and typed RPC errors
- **90%+ test coverage** - Subprocess-backed transport and streaming tests

## Installation

Using [uv](https://docs.astral.sh/uv/):

```bash
uv add autohand-sdk
```

Using pip:

```bash
pip install autohand-sdk
```

## Quick Start

```python
import asyncio
from autohand_sdk import AutohandSDK

async def main():
    async with AutohandSDK(
        cwd=".",
        model="fantail2",
    ) as sdk:
        async for event in sdk.stream_prompt("Hello, world!"):
            if event["type"] == "message_update":
                print(event.get("delta", ""), end="")
            elif event["type"] == "tool_start":
                print(f"\nRunning {event.get('tool_name') or event.get('toolName')}")

asyncio.run(main())
```

## Skills API

### Option A: Skills in Prompt

Configure skills so the agent can reference them via `/skill <name>`:

```python
sdk = AutohandSDK(
    cwd=".",
    model="fantail2",
    skill_refs=["typescript", "testing", "react"],
)
```

### Option B: Direct Skill Provision

Provide skills directly, including custom skill files:

```python
sdk = AutohandSDK(
    cwd=".",
    model="fantail2",
    skill_refs=[
        "typescript",                              # Built-in
        "./skills/my-custom/SKILL.md",             # Local file
        {"name": "api", "path": "/path/SKILL.md"},  # Named skill
    ],
)
```

The SDK automatically:
1. Copies skill files to `~/.autohand/skills/`
2. Extracts skill names from file paths
3. Passes skill names to CLI via `--skills` flag

Set `copy_skill_files=False` if you only want to activate skills that are
already installed and do not want startup to write into `~/.autohand/skills`.

## Configuration

```python
from autohand_sdk import AutohandSDK

sdk = AutohandSDK(
    cwd=".",                         # Working directory
    model="fantail2",                 # Model to use
    temperature=0.7,                  # Sampling temperature
    max_iterations=10,                # Max iterations in auto-mode
    startup_check=True,               # Probe CLI readiness on start
    debug=True,                       # Enable debug logging
    unrestricted=True,                # Unrestricted mode
    auto_mode=True,                   # Enable auto-mode
    permission_mode="default",         # CLI permission mode
    env_vars={"AUTOHAND_NO_BANNER": "1"},
)
```

## API Reference

Full guides live in `docs/`:

- `docs/GETTING_STARTED.md` - install, authenticate, configure providers, and run the first prompt.
- `docs/API_REFERENCE.md` - constructor, lifecycle, prompts, events, permissions, and config models.
- `docs/configuration.md` - provider, execution, skills, context, session, and environment options.
- `docs/event-streaming.md` - event shapes and streaming patterns.
- `docs/error-handling.md` - transport, RPC, timeout, abort, and recovery patterns.
- `docs/advanced-patterns.md` - system prompts, sessions, model switching, JSON output, and AGENTS.md.
- `docs/permissions.md` - permission modes and programmatic approval.
- `docs/plan-mode.md` - read-only planning and gated implementation.
- `docs/memory.md` - CLI memory behavior through Python event streams.
- `docs/sdlc-workflows.md` - discovery, gated implementation, and release-readiness flows.

### AutohandSDK

Main SDK class for interacting with the Autohand CLI.

#### Methods

- `start()` - Start the SDK and connect to CLI
- `stop()` / `close()` - Stop the SDK and cleanup
- `stream_prompt(message, **kwargs)` - Send a prompt and stream events
- `abort(reason=None)` - Abort current operation
- `get_state()` - Get current agent state
- `get_messages(limit=None, before=None)` - Get messages
- `set_model(model)` - Change the model
- `set_temperature(temperature)` - Set temperature
- `get_account_info()` - Get account information

#### Properties

- `config` - Current SDK configuration
- `skills` - Get/set skill references

### Events

The SDK emits events during agent execution:

- `agent_start` - Agent started
- `turn_start` / `turn_end` - Prompt turn lifecycle
- `message_start` - Assistant message started
- `message_update` - New token/chunk
- `message_end` - Message complete
- `tool_start` - Tool execution started
- `tool_update` - Streaming tool output
- `tool_end` - Tool execution completed
- `permission_request` - Permission needed
- `file_modified` - File mutation hook notification
- `agent_end` - Agent finished
- `error` - Error occurred

Events are dictionaries. Known camelCase RPC keys are also exposed with Python-friendly snake_case aliases, so `toolName` is available as `tool_name`, `requestId` as `request_id`, and so on.

For typed handling, parse known event dictionaries into Pydantic models:

```python
from autohand_sdk import parse_sdk_event

async for raw_event in sdk.stream_prompt("Hello"):
    event = parse_sdk_event(raw_event)
    if not isinstance(event, dict) and event.type == "message_update":
        print(event.delta or "", end="")
```

### Errors

Transport and RPC failures raise SDK-specific exceptions:

```python
from autohand_sdk import RPCError, RequestTimeoutError, TransportNotStartedError
```

- `TransportNotStartedError` - request attempted before `start()`
- `RequestTimeoutError` - request exceeded `timeout`
- `RPCError` - CLI returned a JSON-RPC error response; exposes `code` and `data`

## Development

Using uv for dependency management:

```bash
# Install dependencies
uv sync

# Run tests with coverage
uv run pytest

# Run type checking
uv run mypy src

# Run linting
uv run ruff check .

# Format code
uv run ruff format .
```

## License

MIT License - see LICENSE file for details.
