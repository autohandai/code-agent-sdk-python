# Replayable Autoresearch Ledger

The Python SDK exposes Autohand's replayable autoresearch engine through typed
Pydantic models and the same JSON-RPC methods as the TypeScript v1.0.3 SDK. A
session proposes focused changes, measures them repeatedly, applies deterministic
constraints and decision policy, and persists an immutable ledger under `.auto/`.

## Requirements

- A current Autohand CLI binary with autoresearch RPC support.
- A clean Git repository with at least one commit.
- A deterministic benchmark command or script that emits the configured metric.
- Explicit `unrestricted=True` only when autonomous local edits are acceptable.

When applications may connect to older CLI builds, handle an `RPCError` from
`autohand.autoresearch.start` as an unsupported-feature result.

## Start, Run, and Inspect

```python
from autohand_sdk import AutohandSDK

async with AutohandSDK(cwd=".", unrestricted=True, timeout=600_000) as sdk:
    started = await sdk.start_autoresearch(
        objective="Reduce test runtime without changing behavior",
        max_iterations=12,
        timeout_ms=600_000,
        metric_name="test_ms",
        metric_unit="ms",
        direction="lower",
        measure_command="uv run pytest",
        checks_command="uv run mypy src && uv run ruff check .",
        files_in_scope=["src", "tests"],
    )
    if not started.success or not started.instruction:
        raise RuntimeError(started.error or "no autoresearch instruction returned")

    async for event in sdk.stream_prompt(started.instruction):
        if event["type"] == "autoresearch":
            print(event)

    status = await sdk.get_autoresearch_status()
    history = await sdk.get_autoresearch_history()
    print(status.runs_logged, len(history.attempts))
```

Calling `start_autoresearch` for an existing paused session resumes its persisted
configuration. `stop_autoresearch` pauses the loop but keeps its state and ledger.

## Replay and Decision Operations

Replay uses an isolated worktree. `evaluator="original"` uses the frozen
benchmark definition captured by the attempt; `evaluator="current"` uses the
current configuration and can report drift warnings.

```python
replayed = await sdk.replay_autoresearch("attempt-1", evaluator="original")
rescored = await sdk.rescore_autoresearch(attempt_id="attempt-1")
comparison = await sdk.compare_autoresearch("attempt-1", "attempt-2")
pareto = await sdk.get_autoresearch_pareto()
```

Rescoring appends a new immutable decision derived from stored measurements; it
does not rewrite the evaluation. Use `all=True` instead of `attempt_id` to
rescore the full ledger.

## Artifact Retention

Pinned attempts are protected from pruning. Always preview retention changes
before explicitly applying them:

```python
await sdk.pin_autoresearch("attempt-1", pinned=True)
preview = await sdk.prune_autoresearch(dry_run=True)
print(preview.candidates, preview.bytes_freed)

applied = await sdk.prune_autoresearch(dry_run=False, yes=True)
```

## Events

Both event models use `type="autoresearch"`:

- `AutoresearchEvent` has lifecycle `phase` values `start`, `status`, or `pause`.
- `AutoresearchOperationEvent` has an `operation` plus `started`, `completed`, or
  `failed` phase.

Use `parse_sdk_event(raw_event)` to discriminate them into typed models. Raw
event dictionaries preserve CLI camelCase keys and also expose common snake_case
aliases such as `attempt_id`, `max_iterations`, `runs_logged`, and `status_text`.

See [`examples/27-autoresearch-ledger.py`](examples/27-autoresearch-ledger.py) for
a runnable end-to-end example.
