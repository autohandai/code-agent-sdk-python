# API Reference

Complete reference for the Python Autohand SDK.

## AutohandSDK

Main async API for controlling the Autohand CLI.

```python
from autohand_sdk import AutohandSDK

sdk = AutohandSDK(cwd=".")
```

### Constructor

```python
AutohandSDK(config: SDKConfig | None = None, **kwargs)
```

Common keyword arguments:

- `cwd`: working directory for the CLI subprocess.
- `cli_path`: path to an Autohand CLI binary. Omit to auto-detect.
- `debug`: enable SDK/transport debug logging.
- `timeout`: JSON-RPC request timeout in milliseconds. Default is `300000`.
- `startup_check`: probe the CLI with `autohand.getState` after subprocess startup. Default is `True`.
- `model`: model identifier.
- `fallback_model`: fallback model if the CLI/provider supports fallback behavior.
- `temperature`: sampling temperature, `0.0` through `2.0`.
- `provider`: provider name, such as `autohandai`, `openrouter`, `openai`, `anthropic`, `azure`, or `ollama`.
- `api_key`: provider API key.
- `base_url`: provider base URL.
- `autohand_ai_plan`: Autohand AI execution style, `cloud` or `local`.
- `openai_auth_mode`, `reasoning_effort`, `chatgpt_access_token`, `chatgpt_account_id`: OpenAI-specific settings.
- `azure_auth_method`, `azure_tenant_id`, `azure_client_id`, `azure_client_secret`, `azure_resource_name`, `azure_deployment_name`: Azure-specific settings.
- `auto_mode`: start CLI with `--auto-mode`.
- `unrestricted`: start CLI with `--unrestricted`.
- `bare`: start the minimal explicit runtime with `--bare`.
- `auto_commit`: enable `-c` automatic commits.
- `idle_logout`: set to `False` to pass `--no-idle-logout` for long-running agents.
- `max_iterations`, `max_runtime`, `max_cost`: execution limits passed to the CLI.
- `sys_prompt`, `system_prompt_file`, `append_sys_prompt`, `append_system_prompt_file`: system prompt controls.
- `yolo`, `yolo_timeout`: auto-approval controls.
- `add_dir` or `additional_directories`: additional workspace directories.
- `permission_mode`: CLI permission mode.
- `permissions`: `PermissionSettings` object with mode, allow list, and deny list.
- `context` or `context_compact`: context-management settings.
- `session`, `persist_session`, `session_id`, `resume`, `continue`, `fork`: session controls.
- `display_language`, `mcp_config`, `agents`, `plugin_dir`: current CLI integration flags.
- `agents_md`: `AgentsMdSettings` forwarded to the CLI's AGENTS.md startup flags.
- `features`: `FeatureFlagSettings` applied through `autohand.applyFlagSettings` after startup.
- `skills`: `SkillSettings` object for advanced skill configuration.
- `skill_refs`: direct skill names, paths, or objects.
- `copy_skill_files`: copy local skill files into `~/.autohand/skills` before startup. Default is `True`.
- `env_vars`: `AutohandEnvVars` or a dictionary of `AUTOHAND_` variables forwarded to the subprocess.
- `extra_args`: additional CLI arguments.

The constructor accepts either a `SDKConfig` instance or keyword arguments:

```python
import os

from autohand_sdk import SDKConfig, AutohandSDK

config = SDKConfig(
    cwd=".",
    provider="autohandai",
    model="fantail",
    api_key=os.environ["AUTOHAND_AI_API_KEY"],
)
sdk = AutohandSDK(config, debug=True)
```

`model` and `provider` may be omitted when the CLI already has a working
`~/.autohand/config.json`.

## Agent Facade

`Agent` starts and owns an `AutohandSDK` session while exposing the command,
capability, and persistent-goal helpers directly:

```python
from autohand_sdk import Agent

agent = await Agent.create(cwd=".")
try:
    result = await agent.deep_research("Map the repository architecture")
    goal = await agent.create_goal("Implement the approved plan")
finally:
    await agent.close()
```

Use `Agent.from_sdk(sdk)` to wrap an SDK instance whose lifecycle is already
managed by the application.

## Lifecycle

### start

```python
await sdk.start()
```

Starts the CLI subprocess in JSON-RPC mode. Calling `start()` more than once is
safe.

### stop

```python
await sdk.stop()
```

Stops the subprocess and cleans up pending requests.

### close

```python
await sdk.close()
```

Alias for `stop()`.

### Async Context Manager

```python
async with AutohandSDK(cwd=".") as sdk:
    async for event in sdk.stream_prompt("Hello"):
        ...
```

## Prompting

### stream_prompt

```python
async for event in sdk.stream_prompt(message: str, **kwargs):
    ...
```

Sends a prompt and yields event dictionaries as the CLI emits notifications.

Prompt keyword arguments map to the CLI RPC `autohand.prompt` params:

- `context`: optional context dictionary, for example `{"files": ["README.md"]}`.
- `images`: optional image attachments, each with `data`, `mimeType`, and optional `filename`.
- `thinking_level`: one of `none`, `normal`, or `extended`.

Example:

```python
async for event in sdk.stream_prompt(
    "Review this file",
    context={"files": ["src/autohand_sdk/transport.py"]},
):
    if event["type"] == "message_update":
        print(event.get("delta", ""), end="", flush=True)
```

## Autoresearch Ledger

The autoresearch methods use the exact RPC methods exposed by the current CLI
and return Pydantic result models. Python field names are snake_case; serialized
RPC payloads and accepted CLI responses use lower camel case.

| Method | Result | Purpose |
| --- | --- | --- |
| `start_autoresearch(objective, **options)` | `AutoresearchStartResult` | Initialize or resume a session and return its loop instruction. |
| `get_autoresearch_status()` | `AutoresearchStatusResult` | Read active state, progress, attempts, and Pareto IDs. |
| `stop_autoresearch()` | `AutoresearchStopResult` | Pause without deleting persisted state. |
| `get_autoresearch_history()` | `AutoresearchHistoryResult` | List immutable attempts and materialization state. |
| `replay_autoresearch(attempt_id, evaluator=None)` | `AutoresearchReplayResult` | Replay with the original or current evaluator. |
| `rescore_autoresearch(attempt_id=..., all=...)` | `AutoresearchRescoreResult` | Append decisions using current policy. |
| `compare_autoresearch(left_attempt_id, right_attempt_id)` | `AutoresearchCompareResult` | Compare samples, aggregates, checks, and decisions. |
| `get_autoresearch_pareto()` | `AutoresearchParetoResult` | List constraint-passing non-dominated attempts. |
| `pin_autoresearch(attempt_id, pinned)` | `AutoresearchPinResult` | Protect or release candidate artifacts. |
| `prune_autoresearch(dry_run=None, yes=None)` | `AutoresearchPruneResult` | Preview or explicitly apply retention. |

`start_autoresearch` accepts metric, benchmark/check command or script,
in-scope files, subagent participation, secondary objectives, constraints,
sampling, retention, and environment allowlist settings. The return value's
`instruction` is intended to be passed to `stream_prompt` for normal streamed
agent execution.

Use `rescore_autoresearch(attempt_id="attempt-1")` for one attempt or
`rescore_autoresearch(all=True)` for the full ledger. Passing neither or both is
rejected before an RPC request is sent.

See [autoresearch.md](autoresearch.md) for a complete workflow.

## Slash Commands

Command helpers use the normal streamed prompt channel and normalize command
names with a leading slash.

```python
commands = await sdk.supported_commands()
if await sdk.supports_command("deep-research"):
    result = await sdk.deep_research("Map the repository architecture")
    print(result.content)

result = await sdk.autoresearch("Reduce benchmark latency")
result = await sdk.command("/review", ["src", "tests"])

async for event in sdk.stream_command("/deep-research", "SDK parity"):
    ...
```

`command`, `deep_research`, and `autoresearch` return `PromptResult`. Use
`stream_command` when each SDK event is needed.

## Persistent Goals

The persistent-goal helpers use all seven current goal RPCs. Python fields are
snake_case and serialize to the CLI's lower-camel-case payloads.

```python
from autohand_sdk import UpdateGoalParams

created = await sdk.create_goal(
    "Ship the Python SDK parity release",
    token_budget=50_000,
    time_budget_seconds=3_600,
)
snapshot = await sdk.get_goal()
updated = await sdk.update_goal(UpdateGoalParams(status="paused"))
queued = await sdk.queue_goal("Write the release notes")
started = await sdk.start_queued_goal()
templates = await sdk.list_goal_templates()
cleared = await sdk.clear_goal()
```

Results are typed as `GoalSnapshot`, `GoalMutationResult`, or a
`GoalFeatureDisabledResult` when the CLI's `slashGoal` feature is disabled.
Pass an explicit `None` in `UpdateGoalParams`, such as
`UpdateGoalParams(token_budget=None)`, to clear a nullable budget.

## Feature Settings

Configure feature settings at startup or apply them to a running SDK:

```python
from autohand_sdk import AutohandSDK, FeatureFlagSettings

features = FeatureFlagSettings(slash_goal=True, experimental_fork=True)
sdk = AutohandSDK(features=features)
await sdk.start()  # applies features after the RPC runtime is healthy

await sdk.apply_feature_settings(FeatureFlagSettings(token_usage_status=True))
await sdk.apply_flag_settings({"features": {"experimentalClone": True}})
```

## Events

Events are dictionaries. The raw camelCase RPC fields are preserved and common
fields are also exposed as snake_case aliases.

Common event types:

- `agent_start`
- `turn_start`
- `message_start`
- `message_update`
- `message_end`
- `tool_start`
- `tool_update`
- `tool_end`
- `permission_request`
- `directory_access_request`
- `file_modified`
- `changes_batch_start`
- `changes_batch_update`
- `changes_batch_end`
- `autoresearch` (`AutoresearchEvent` or `AutoresearchOperationEvent`)
- `turn_end`
- `agent_end`
- `error`

Examples of aliasing:

- `sessionId` and `session_id`
- `turnId` and `turn_id`
- `messageId` and `message_id`
- `toolName` and `tool_name`
- `requestId` and `request_id`
- `filePath` and `file_path`
- `contextPercent` and `context_percent`
- `messageCount` and `message_count`

You can opt into typed Pydantic event models with `parse_sdk_event`:

```python
from autohand_sdk import parse_sdk_event

async for raw_event in sdk.stream_prompt("Explain the repo"):
    event = parse_sdk_event(raw_event)
    if not isinstance(event, dict) and event.type == "message_update":
        print(event.delta or "", end="", flush=True)
```

Unknown future event types are returned unchanged as dictionaries.

## Control Methods

### abort

```python
result = await sdk.abort(reason="User cancelled")
```

Sends `autohand.abort`.

### respond_to_permission

```python
await sdk.respond_to_permission(
    request_id="req_123",
    decision="allow",
    allowed=True,
    remember=False,
)
```

Responds to a `permission_request` event.

### set_model

```python
await sdk.set_model("fantail")
```

Sends `autohand.modelSet` and updates the SDK config.

### set_agent

```python
await sdk.set_agent("code-reviewer")
```

Applies an agent flag through `autohand.applyFlagSettings` when supported by
the CLI.

### set_temperature

```python
await sdk.set_temperature(0.2)
```

Applies runtime temperature through `autohand.applyFlagSettings`.

## Information Methods

### get_state

```python
state = await sdk.get_state()
```

Returns a `GetStateResult` Pydantic model:

- `status`: `idle`, `processing`, or `waiting_permission`.
- `session_id`
- `model`
- `workspace`
- `context_percent`
- `message_count`

### get_messages

```python
messages = await sdk.get_messages(limit=20)
```

Returns a `GetMessagesResult` Pydantic model.

### get_models

```python
models = await sdk.get_models()
```

Returns the model list from `autohand.getSupportedModels`.

### get_agents

```python
agents_or_commands = await sdk.get_agents()
```

Compatibility method. The current CLI exposes supported command names over RPC;
this method returns `agents` when available or falls back to `commands`.

### get_account_info

```python
account = await sdk.get_account_info()
```

Returns account information from `autohand.getAccountInfo`.

### save_session

```python
state = await sdk.save_session()
```

Compatibility method. The current CLI does not expose a dedicated save-session
RPC method, so this returns current state. Use session startup flags such as
`persist_session=True` for CLI-managed persistence.

## Skills

Skill references can be strings or dictionaries:

```python
sdk = AutohandSDK(
    cwd=".",
    skill_refs=[
        "typescript",
        "./skills/my-custom/SKILL.md",
        {"name": "api-client", "path": "../skills/api-client/SKILL.md"},
    ],
)
```

The SDK copies local files to `~/.autohand/skills/<skill-name>/SKILL.md` before
starting the CLI, then activates skill names with `--skills`.

Disable that home-directory write when you only want to activate already
installed skill names:

```python
sdk = AutohandSDK(
    cwd=".",
    skill_refs=["testing"],
    copy_skill_files=False,
)
```

## Exceptions

```python
from autohand_sdk import RPCError, RequestTimeoutError, TransportNotStartedError
```

- `TransportNotStartedError`: request attempted before `start()`.
- `RequestTimeoutError`: no JSON-RPC response before `timeout`.
- `RPCError`: CLI returned a JSON-RPC error response. Has `code` and `data`.

```python
try:
    await sdk.get_state()
except RPCError as exc:
    print(exc.code, exc.data)
```
