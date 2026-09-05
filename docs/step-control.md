# Runs and step control

`Agent` adds lazy runs, repeatable results, JSON output, and replayable event
streams over an existing CLI session. The CLI must support `autohand.stepEnd`,
`autohand.stepDecision`, and host-mode `stopWhen` for step control.

```python
from autohand_sdk import Agent, AutohandSDK, has_tool_call, is_step_count

async def inspect() -> None:
    # Uses your authenticated CLI configuration and selected provider.
    async with AutohandSDK(cwd=".") as sdk:
        agent = Agent.from_sdk(sdk)
        run = agent.send(
            "Inspect the project and summarize the important files.",
            stop_when=[is_step_count(3), has_tool_call("read_file")],
        )
        result = await run.wait()
        print(result.status, result.text)
        for step in result.steps:
            print(step.step_number, step.tool_results)

        if result.status == "stopped":
            continued = await agent.run("Continue using the saved tool results.")
            print(continued.text)
```

Each step includes its tool calls and the results already persisted by the CLI.
The counter starts again for each prompt. A list or tuple of predicates uses OR:
evaluation stops at the first true result. An empty list disables host control.
Conditions receive `StopConditionContext.steps`, an ordered tuple of copied
`AgentStep` models. They can return a boolean immediately or await one:

```python
from autohand_sdk import StopConditionContext

async def stop_after_failed_tool(context: StopConditionContext) -> bool:
    return any(not result.success for result in context.steps[-1].tool_results)

# The low-level API accepts the same conditions.
async for event in sdk.stream_prompt("Inspect this project", stop_when=stop_after_failed_tool):
    print(event)
```

Callbacks stay inside Python. The SDK sends only `stopWhen: {mode: "host"}` to
the CLI and responds after each step. Notifications continue while asynchronous
conditions wait. A failed predicate sends a stop decision and raises its error;
invalid step payloads or rejected decisions abort and drain the turn. If cleanup
cannot settle within two seconds, the transport closes and must be restarted.

`Run.wait()` returns the same result on subsequent calls, with status
`completed`, `stopped`, or `aborted`, final text, events, and steps. A process exit
or failed turn raises instead of producing a completed result. Cancelling one
waiter leaves other readers intact. Use `await run.abort()` to cancel the run;
aborting a queued or unstarted run does not interrupt another prompt.

`run.stream()` replays all buffered events before receiving live events.
Independent subscribers see the same trace; closing one subscriber leaves the
run active. `agent.stream(...)` owns its run and aborts when explicitly closed
early. Runs retain their event history until released. For long sessions that do
not need replay, consume `sdk.stream_prompt(...)` directly. Its bounded prompt
queue raises on overflow instead of silently losing tool decisions.

```python
from pydantic import BaseModel

class Summary(BaseModel):
    summary: str

summary = await agent.json("Summarize this project as {\"summary\": string}",
                           validate=Summary.model_validate)
# For an existing run, await run.json(validate=Summary.model_validate).
```

JSON helpers accept plain JSON, fenced JSON, or a balanced JSON object/array
embedded in commentary. Invalid output raises `StructuredOutputError`, retaining
`raw_response`; validation errors propagate unchanged. `agent.json` also accepts
`schema`, `schema_name`, and `output_instructions` to describe the expected output
in its prompt. Existing `command`, `deep_research`, and
`autoresearch` methods retain their `PromptResult` return type.

## Runtime verification

The opt-in integration test uses the actual CLI with local authentication and
Autohand AI HTTP mocks. It reads a real file, stops, and verifies the saved tool
result reaches the next model request:

```bash
AUTOHAND_TEST_CLI_PATH=/path/to/autohand uv run pytest tests/test_harness_step_control.py --no-cov
```

It uses an explicit Autohand AI config and context window. This verifies the
provider/tool/step boundary, without claiming that SDK provider selection alone
overrides an existing CLI configuration or that every distributed binary is current.
`env_vars.AUTOHAND_AUTH_API_URL` selects the authentication API; `AUTOHAND_API_URL`
selects the general API. Startup RPC errors retain the CLI's diagnostic message.
