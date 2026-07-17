# Python Examples

These examples are runnable Python scripts for the Autohand SDK tin-wrapper.
They mirror the TypeScript wrapper examples while using Python `asyncio` and the
Python method names.

## Prerequisites

- Python 3.10+
- Autohand CLI authenticated with `autohand login`
- SDK dependencies installed with `uv sync` when running from this repository

For local CLI development:

```bash
export AUTOHAND_CLI_PATH=/Users/igorcosta/Documents/autohand/cli-3/autohand
```

Optional model override:

```bash
export AUTOHAND_MODEL=fantail
```

When `AUTOHAND_MODEL` is not set, examples use the model/provider already
configured for the CLI.

## Run

From `tin-wrapper/python`:

```bash
uv run python docs/examples/01-hello-agent.py
```

Or, after installing the package:

```bash
python docs/examples/01-hello-agent.py
```

## Example Index

- `01-hello-agent.py`: minimal prompt and state lookup.
- `02-streaming-query.py`: structured event handling.
- `03-code-reviewer.py`: file-aware review prompt.
- `04-bash-command.py`: command/tool execution flow.
- `05-file-editor.py`: file editing workflow with permission routing.
- `06-prompt-skills.py`: skills referenced in prompt text.
- `07-direct-skills.py`: direct skill names and local `SKILL.md` paths.
- `10-multi-tool-reasoning.py`: multi-step codebase analysis.
- `13-permissions.py`: permission request response handling.
- `20-sdlc-discovery-plan.py`: discovery and plan workflow.
- `21-sdlc-gated-implementation.py`: gated implementation workflow.
- `22-sdlc-release-readiness.py`: release readiness check workflow.
- `27-autoresearch-ledger.py`: typed replayable autoresearch lifecycle and ledger inspection.

Examples that create or edit files use scratch workspaces under the system temp
directory, usually `/tmp/autohand-sdk-examples/...`. The direct skill example
also demonstrates the SDK's real local-skill behavior, which copies local skill
files into `~/.autohand/skills/<skill-name>/SKILL.md` before launching the CLI.
