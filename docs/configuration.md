# Configuration

The SDK accepts configuration through the `AutohandSDK` constructor or a `SDKConfig` Pydantic model. Every field is optional.

## Basic Options

```python
from autohand_sdk import AutohandSDK

sdk = AutohandSDK(
    cwd=".",              # Working directory. Defaults to current directory.
    cli_path="/path/to/cli",  # Custom CLI binary. Auto-detected if omitted.
    debug=True,           # Log JSON-RPC traffic to stderr.
    timeout=30000,        # Request timeout in milliseconds.
    startup_check=True,   # Probe CLI with getState after startup.
)
```

## Provider Setup

The SDK delegates LLM calls to the CLI, so provider credentials normally live in `~/.autohand/config.json`:

```json
{
  "provider": "openrouter",
  "openrouter": {
    "apiKey": "sk-or-...",
    "model": "openrouter/auto"
  }
}
```

You can also pass them inline:

```python
sdk = AutohandSDK(
    cwd=".",
    provider="openrouter",
    model="openrouter/auto",
    api_key=os.environ["OPENROUTER_API_KEY"],
)
```

Override the model at runtime:

```python
await sdk.set_model("openrouter/auto")
```

### Supported Providers

| Provider | Config Key | Notes |
|---|---|---|
| OpenRouter | `openrouter` | Set `api_key` and optional `model`. |
| OpenAI | `openai` | Set `api_key` or use `chatgpt_access_token`. |
| Azure | `azure` | Needs `azure_auth_method`, `azure_tenant_id`, `azure_client_id`, etc. |
| Ollama | `ollama` | Local. Set `base_url` or `port` if not on 11434. |
| LlamaCPP | `llamacpp` | Local. Set `port`. |
| MLX | `mlx` | Local. Set `port`. |

The SDK auto-detects the provider from the model string when possible. Pass `provider` explicitly if auto-detection fails.

## Execution Mode

```python
sdk = AutohandSDK(
    cwd=".",
    auto_mode=True,       # Let the agent run autonomously within limits.
    max_iterations=10,    # Max auto-mode turns.
    max_runtime=30,       # Max runtime in minutes.
    max_cost=5.0,         # Max API cost in USD.
)
```

## Skills

```python
from autohand_sdk import SkillSettings

sdk = AutohandSDK(
    cwd=".",
    skills=SkillSettings(
        auto_skill=True,
        skills=["typescript", "react", "testing"],
        sources=[
            {"name": "autohand-user"},
            {"name": "autohand-project"},
            {"name": "community"},
        ],
        install_missing=True,
    ),
)
```

Or use the shorthand:

```python
sdk = AutohandSDK(
    cwd=".",
    skill_refs=["typescript", "react", "testing"],
)
```

## Context

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

## Session Persistence

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
```

## System Prompts

```python
sdk = AutohandSDK(
    cwd=".",
    sys_prompt="You are a careful code reviewer.",
    append_sys_prompt="Always run tests before declaring a task done.",
)
```

Both accept inline strings or file paths. The SDK reads the file before starting the CLI.

## AGENTS.md

```python
from autohand_sdk import AgentsMdSettings

sdk = AutohandSDK(
    cwd=".",
    agents_md=AgentsMdSettings(
        enable=True,
        create=True,
        path="./AGENTS.md",
        auto_update=True,
        include_commands=True,
        include_skills=True,
        include_conventions=True,
    ),
)
```

## Permissions

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

## Environment Variables

Forward `AUTOHAND_` variables to the CLI subprocess:

```python
from autohand_sdk import AutohandEnvVars

sdk = AutohandSDK(
    cwd=".",
    env_vars=AutohandEnvVars(
        AUTOHAND_NO_BANNER="1",
        AUTOHAND_DEBUG="1",
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

## Full Example

```python
from autohand_sdk import AutohandSDK, SkillSettings, ContextSettings, SessionSettings

sdk = AutohandSDK(
    cwd=".",
    model="openrouter/auto",
    temperature=0.7,
    debug=True,
    auto_mode=True,
    max_iterations=10,
    permission_mode="interactive",
    skills=SkillSettings(
        auto_skill=True,
        skills=["typescript"],
    ),
    context=ContextSettings(
        context_compact=True,
        max_tokens=128000,
    ),
    session=SessionSettings(
        persist_session=True,
        session_path="./.autohand/sessions",
    ),
    append_sys_prompt="Always write tests for new code.",
)
```
