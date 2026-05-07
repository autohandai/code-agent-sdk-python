# Getting Started with Autohand SDK for Python

This guide walks through installing the Python SDK, connecting it to the
Autohand CLI, and running your first agent.

## 1. Install

Using uv:

```bash
uv add autohand-sdk
```

For local development from this repository:

```bash
cd /Users/igorcosta/Documents/autohand/agentsdk/tin-wrapper/python
uv sync
```

Using pip:

```bash
pip install autohand-sdk
```

## 2. Install and Authenticate the CLI

The SDK talks to the Autohand CLI over stdio JSON-RPC. Install and authenticate
the CLI first:

```bash
autohand login
```

For local CLI development, point examples at your checkout:

```bash
export AUTOHAND_CLI_PATH=/Users/igorcosta/Documents/autohand/cli-3/autohand
```

When `cli_path` or `AUTOHAND_CLI_PATH` is omitted, the SDK attempts to use its
bundled platform binary or a matching CLI binary from `PATH`.

## 3. Configure a Provider

The SDK can pass provider settings directly to the CLI, or you can rely on the
CLI's normal `~/.autohand/config.json`.

### Inline Configuration

```python
import os
from autohand_sdk import AutohandSDK

sdk = AutohandSDK(
    cwd=".",
    provider="openrouter",
    model="openrouter/quasar-alpha",
    api_key=os.environ["OPENROUTER_API_KEY"],
)
```

OpenAI:

```python
sdk = AutohandSDK(
    cwd=".",
    provider="openrouter",
    model="openrouter/auto",
    api_key=os.environ["OPENROUTER_API_KEY"],
)
```

Azure:

```python
sdk = AutohandSDK(
    cwd=".",
    provider="azure",
    model="gpt-4",
    azure_auth_method="api-key",
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
    azure_resource_name="my-resource",
    azure_deployment_name="my-deployment",
)
```

Local Ollama:

```python
sdk = AutohandSDK(
    cwd=".",
    provider="ollama",
    model="llama3:latest",
    base_url="http://localhost:11434",
)
```

### CLI Config File

Create `~/.autohand/config.json`:

```json
{
  "provider": "openrouter",
  "model": "openrouter/quasar-alpha",
  "apiKey": "sk-or-..."
}
```

Then instantiate the SDK with only the working directory:

```python
sdk = AutohandSDK(cwd=".")
```

## 4. First Script

Create `first_agent.py`:

```python
import asyncio
import os
from autohand_sdk import AutohandSDK


async def main() -> None:
    config = {"cwd": "."}
    if os.environ.get("AUTOHAND_CLI_PATH"):
        config["cli_path"] = os.environ["AUTOHAND_CLI_PATH"]
    if os.environ.get("AUTOHAND_MODEL"):
        config["model"] = os.environ["AUTOHAND_MODEL"]

    async with AutohandSDK(**config) as sdk:
        async for event in sdk.stream_prompt("Write a hello world program in Python"):
            if event["type"] == "message_update":
                print(event.get("delta", ""), end="", flush=True)
            elif event["type"] == "tool_start":
                print(f"\n[tool:start] {event.get('tool_name')}")
            elif event["type"] == "error":
                print(f"\n[error] {event.get('message')}")


asyncio.run(main())
```

Run it:

```bash
python first_agent.py
```

From this repository:

```bash
uv run python docs/examples/01-hello-agent.py
```

## 5. Work with Files

Pass file context to the agent:

```python
async for event in sdk.stream_prompt(
    "Review this file for obvious correctness issues",
    context={"files": ["src/autohand_sdk/sdk.py"]},
):
    if event["type"] == "message_update":
        print(event.get("delta", ""), end="", flush=True)
```

## 6. Handle Permissions

When the CLI asks for approval, the SDK emits `permission_request`. Production
apps should route this to the user. Examples may auto-allow for demonstration:

```python
if event["type"] == "permission_request":
    await sdk.respond_to_permission(
        event["request_id"],
        decision="allow",
        allowed=True,
    )
```

## 7. Run the Examples

```bash
uv run python docs/examples/01-hello-agent.py
uv run python docs/examples/02-streaming-query.py
uv run python docs/examples/13-permissions.py
```

See [docs/examples/README.md](./examples/README.md) for the full list.
