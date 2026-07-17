# Autohand SDK for Python

Python wrapper for the Autohand CLI. The SDK starts the CLI in JSON-RPC mode,
sends prompts, receives streaming events, and exposes a small async API for
agent control.

```text
Your Python code -> autohand_sdk -> CLI subprocess -> AI provider
```

## Install

```bash
uv add autohand-sdk
```

Or:

```bash
pip install autohand-sdk
```

## Requirements

- Python 3.10+
- Autohand CLI installed or a local CLI path supplied with `AUTOHAND_CLI_PATH`
- CLI authentication already completed with `autohand login`

## Quick Start

```python
import asyncio
from autohand_sdk import AutohandSDK


async def main() -> None:
    async with AutohandSDK(cwd=".") as sdk:
        async for event in sdk.stream_prompt("Explain this project in one paragraph"):
            if event["type"] == "message_update":
                print(event.get("delta", ""), end="", flush=True)


asyncio.run(main())
```

## Docs

- [Getting Started](./GETTING_STARTED.md)
- [API Reference](./API_REFERENCE.md)
- [Configuration](./configuration.md)
- [Event Streaming](./event-streaming.md)
- [Error Handling](./error-handling.md)
- [Advanced Patterns](./advanced-patterns.md)
- [Permissions](./permissions.md)
- [Plan Mode](./plan-mode.md)
- [Memory](./memory.md)
- [SDLC Workflows](./sdlc-workflows.md)
- [Replayable Autoresearch](./autoresearch.md)
- [Examples](./examples/README.md)
