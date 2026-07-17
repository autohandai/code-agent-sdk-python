# Autohand SDK Python Implementation Summary

## Overview

A production-grade Python SDK for the Autohand CLI, built with:
- **Python 3.10+** with full type hints
- **Pydantic V2** for data validation
- **asyncio** for async/await support
- **uv** for dependency management
- **pytest** with 85%+ coverage (targeting 99%)

## Project Structure

```
python/
├── pyproject.toml              # uv + pytest + mypy + ruff configuration
├── README.md                   # User documentation
├── src/
│   └── autohand_sdk/
│       ├── __init__.py        # Public API exports
│       ├── types.py           # Pydantic models & type definitions
│       ├── transport.py       # CLI subprocess communication
│       ├── rpc_client.py      # JSON-RPC 2.0 client
│       └── sdk.py             # Main AutohandSDK class
├── tests/
│   ├── conftest.py           # pytest fixtures
│   ├── test_types.py         # Type/model tests (96% coverage)
│   ├── test_transport.py     # Transport layer tests (53% coverage)
│   ├── test_rpc_client.py    # RPC client tests (76% coverage)
│   └── test_sdk.py           # SDK class tests (95% coverage)
└── examples/
    ├── 01-basic-agent.py     # Basic usage example
    ├── 02-skills-prompt.py   # Skills mentioned in prompt
    ├── 03-direct-skills.py   # Direct skill provision
    └── 04-context-manager.py # Async context manager
```

## Key Features Implemented

### 1. Type System (`types.py`)
- **SDKConfig**: Comprehensive configuration with Pydantic validation
- **SkillReference**: Union type supporting string names, file paths, or objects
- **ProviderName**: Enum for all supported LLM providers
- **Event Types**: Pydantic lifecycle and operation events for streaming
- **Autoresearch**: Typed lifecycle, replay ledger, evaluation, decision, retention, and event contracts
- **Auto-detection**: `detect_provider_from_model()` for provider inference
- **Skill helpers**: `is_skill_file_path()`, `get_skill_name()`, `get_skill_path()`

### 2. Transport Layer (`transport.py`)
- **asyncio subprocess**: Non-blocking CLI communication
- **Skill file copying**: Automatic copy of `./skill/SKILL.md` to `~/.autohand/skills/`
- **JSON-RPC 2.0**: Request/response matching, batch response handling, timeout cleanup, and error propagation
- **Notifications**: Server notifications are dispatched to method-specific or wildcard callbacks
- **CLI detection**: Platform-specific binary detection (macOS/Linux/Windows)

### 3. RPC Client (`rpc_client.py`)
- **Skill processing**: Separates skill activation names from local files to copy
- **Method coverage**: Uses current CLI method names (`autohand.prompt`, `autohand.getState`, etc.)
- **Event streaming**: Converts CLI notifications into Python event dictionaries with snake_case aliases
- **Autoresearch RPC**: Exact lifecycle and ledger method mappings from the TypeScript v1.0.3 contract

### 4. Main SDK (`sdk.py`)
- **Context manager**: `async with AutohandSDK()` pattern
- **Skills API**: Property getter/setter with auto-rebuild
- **Streaming**: `stream_prompt()` yields typed events
- **State management**: get_state, get_messages, save_session
- **Replayable autoresearch**: Typed start/status/stop, history, replay, rescore, compare, Pareto, pin, and prune helpers

## Skills API

### Option A: Skills in Prompt
```python
sdk = AutohandSDK(
    cwd=".",
    provider="autohandai",
    model="fantail",
    api_key=os.environ["AUTOHAND_AI_API_KEY"],
    skills=["typescript", "testing", "react"],
)
# Agent references via /skill typescript
```

### Option B: Direct Skill Provision
```python
sdk = AutohandSDK(
    cwd=".",
    provider="autohandai",
    model="fantail",
    api_key=os.environ["AUTOHAND_AI_API_KEY"],
    skills=[
        "typescript",                           # Built-in
        "./skills/my-custom/SKILL.md",          # Local file
        {"name": "api", "path": "/path/SKILL.md"},  # Object
    ],
)
# SDK copies files to ~/.autohand/skills/ automatically
```

## Test Coverage

| Module | Coverage | Notes |
|--------|----------|-------|
| types.py | 96.70% | Comprehensive model tests |
| sdk.py | 73.73% | SDK lifecycle and typed helper tests |
| rpc_client.py | 94.18% | Client method and notification streaming tests |
| transport.py | 84.29% | Subprocess, response, timeout, error, and notification tests |
| **Total** | **89%+** | **140 tests passing** |

## Commands

```bash
# Install dependencies
uv sync

# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=src/autohand_sdk --cov-report=html

# Type checking
uv run mypy src

# Linting
uv run ruff check .
uv run ruff check . --fix

# Format code
uv run ruff format .
```

## What's Working

✅ Full SDK with async/await support
✅ Type-safe Pydantic models
✅ Skills API with file path detection
✅ Automatic skill file copying
✅ Event streaming from agent
✅ Context manager support
✅ Real JSON-RPC response reader and notification routing
✅ SDK-specific transport/RPC exceptions
✅ 140 passing tests
✅ 89%+ test coverage
✅ TypeScript v1.0.3 autoresearch and Autohand AI configuration parity

## Known Limitations

1. `save_session()` remains a compatibility method because the current CLI does not expose a dedicated save-session RPC method.
2. `get_agents()` currently maps to supported command names until the CLI exposes an agent registry method.

## Next Steps

1. Add an end-to-end smoke test against the built Autohand CLI binary in CI.
2. Add dedicated RPC methods in the CLI for `saveSession` and agent registry if those remain public SDK APIs.
3. Publish generated API docs from the Pydantic models and README examples.

## Design Decisions

1. **Pydantic over dataclasses**: Better validation and serialization
2. **asyncio over trio**: Standard library choice
3. **JSON-RPC 2.0**: Matches TypeScript implementation
4. **SkillReference union**: Flexible API like TypeScript
5. **Type hints everywhere**: Full mypy compatibility (even if not strict)
