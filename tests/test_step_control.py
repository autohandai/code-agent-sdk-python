"""Step control against a persistent JSON-RPC subprocess, including turn-only endings."""

from __future__ import annotations

import asyncio
import json
import sys
import textwrap
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from pydantic import ValidationError

from autohand_sdk import (
    Agent,
    AgentStep,
    AutohandSDK,
    PromptParams,
    StepEndEvent,
    StopConditionContext,
    has_tool_call,
    is_step_count,
    parse_sdk_event,
)
from autohand_sdk.errors import TransportError


@pytest.fixture
async def step_sdk(tmp_path: Path) -> AsyncIterator[AutohandSDK]:
    """Keep a fake CLI alive across prompts, stop decisions, and aborts."""
    cli = tmp_path / "step-cli"
    cli.write_text(
        f"#!{sys.executable}\n"
        + textwrap.dedent("""\
        import json
        import sys
        from pathlib import Path

        log = Path(__file__).with_suffix(".jsonl")
        step = 0
        mode = ""

        def reply(req, result):
            print(json.dumps({"jsonrpc": "2.0", "id": req["id"], "result": result}), flush=True)

        def emit(method, **params):
            params["timestamp"] = "2026-09-06T00:00:00Z"
            print(json.dumps({"jsonrpc": "2.0", "method": "autohand." + method, "params": params}), flush=True)

        def step_end():
            emit("stepEnd", stepId=str(step), step={
                "stepNumber": "bad" if mode == "malformed" else step,
                "toolCalls": [{"tool": "read_file", "args": {"path": "evidence.txt"}}],
                "toolResults": [{"tool": "read_file", "success": True, "output": "saved evidence"}],
            })

        for line in sys.stdin:
            req = json.loads(line)
            with log.open("a") as handle:
                handle.write(line)
            method = req["method"].removeprefix("autohand.")
            params = req.get("params", {})
            if method == "prompt":
                mode = params["message"]
                reply(req, {"success": True})
                emit("turnStart", turnId="turn-1")
                if mode == "exit":
                    sys.exit(0)
                if "stopWhen" in params:
                    assert params["stopWhen"] == {"mode": "host"}
                    step = 1
                    step_end()
                    if mode == "permission":
                        emit("permissionRequest", requestId="permission-1", tool="read_file", description="read evidence", context={})
                else:
                    emit("messageEnd", content='{"answer":"saved evidence"}', messageId="m1")
                    emit("turnEnd", turnId="turn-1", reason="completed")
            elif method == "stepDecision":
                if mode in ("rejected", "invalid-response"):
                    reply(req, {"success": False if mode == "rejected" else "true"})
                elif params["stop"]:
                    reply(req, {"success": True})
                    emit("turnEnd", turnId="turn-1", reason="stop_condition")
                elif step == 1:
                    reply(req, {"success": True})
                    step += 1
                    step_end()
                else:
                    reply(req, {"success": True})
                    emit("messageEnd", content="done", messageId="m1")
                    emit("turnEnd", turnId="turn-1", reason="completed")
            elif method == "abort":
                reply(req, {"success": True})
                emit("turnEnd", turnId="turn-1", reason="aborted")
            else:
                reply(req, {"success": True})
        """)
    )
    cli.chmod(0o755)
    async with AutohandSDK(cli_path=str(cli), cwd=str(tmp_path), skip_preflight=True) as sdk:
        yield sdk


def requests(tmp_path: Path) -> list[dict[str, object]]:
    """Read the actual requests received by the subprocess."""
    return [json.loads(line) for line in (tmp_path / "step-cli.jsonl").read_text().splitlines()]


@pytest.mark.parametrize("count", [0, -1, 1.5, True])
def test_invalid_step_count(count: int) -> None:
    """Reject counts which cannot describe a completed step boundary."""
    with pytest.raises(ValueError, match="positive integer"):
        is_step_count(count)


def test_models_and_helpers() -> None:
    """Validate wire records strictly and keep host callbacks out of JSON."""
    step = AgentStep(stepNumber=1, toolCalls=[{"tool": "read_file", "args": {}}], toolResults=[])
    context = StopConditionContext(steps=(step,))
    assert is_step_count(1)(context)
    assert has_tool_call(" read_file ")(context)
    assert not has_tool_call("write_file")(context)
    assert not has_tool_call("read_file")(StopConditionContext(steps=()))
    with pytest.raises(ValueError, match="non-empty"):
        has_tool_call("  ")
    with pytest.raises(ValidationError):
        AgentStep(stepNumber=True, toolCalls=[], toolResults=[])
    params = PromptParams(message="hello", stop_when=is_step_count(1))
    assert json.loads(params.model_dump_json(exclude_none=True)) == {"message": "hello"}
    assert "stopWhen" not in PromptParams.model_json_schema()["properties"]
    event = parse_sdk_event(
        {
            "type": "step_end",
            "stepId": "1",
            "step": step.model_dump(by_alias=True),
            "timestamp": "now",
        }
    )
    assert isinstance(event, StepEndEvent)


async def test_pause_resume_and_repeatable_run(step_sdk: AutohandSDK, tmp_path: Path) -> None:
    """Stop after two persisted tool steps and reuse the same CLI for continuation."""
    agent = Agent.from_sdk(step_sdk)
    run = agent.send("inspect", stop_when=is_step_count(2))
    result = await asyncio.wait_for(run.wait(), 3)
    assert result.status == "stopped"
    assert len(result.steps) == 2
    assert result.steps[0].tool_results[0].output == "saved evidence"
    assert await run.wait() is result
    assert [event async for event in run.stream()] == result.events
    assert await agent.json("continue") == {"answer": "saved evidence"}
    decisions = [
        request["params"]
        for request in requests(tmp_path)
        if request["method"] == "autohand.stepDecision"
    ]
    assert decisions == [{"stepId": "1", "stop": False}, {"stepId": "2", "stop": True}]


async def test_sdk_stream_accepts_async_conditions(step_sdk: AutohandSDK) -> None:
    """Support asynchronous OR predicates in the low-level SDK API."""

    async def stop(context: StopConditionContext) -> bool:
        await asyncio.sleep(0)
        return len(context.steps) == 1

    events = [
        event
        async for event in step_sdk.stream_prompt("inspect", stop_when=[is_step_count(10), stop])
    ]
    assert events[-1]["reason"] == "stopped"
    assert len([event for event in events if event["type"] == "step_end"]) == 1


async def test_events_flow_while_predicate_waits(step_sdk: AutohandSDK) -> None:
    """A predicate awaiting host input must not prevent that input event from arriving."""
    release = asyncio.Event()

    async def pending(_context: StopConditionContext) -> bool:
        await release.wait()
        return True

    async def collect() -> list[str]:
        types = []
        async for event in step_sdk.stream_prompt("permission", stop_when=pending):
            types.append(event["type"])
            if event["type"] == "permission_request":
                release.set()
        return types

    assert "permission_request" in await asyncio.wait_for(collect(), 3)


async def test_prompt_object_and_independent_subscribers(step_sdk: AutohandSDK) -> None:
    """Prompt objects retain callbacks, and cancelling one waiter leaves the run readable."""
    agent = Agent.from_sdk(step_sdk)
    run = agent.send(PromptParams(message="inspect", stop_when=is_step_count(1)))
    waiter = asyncio.create_task(run.wait())
    await asyncio.sleep(0)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter

    async def consume() -> list[dict[str, object]]:
        return [event async for event in run.stream()]

    first, second, result = await asyncio.gather(consume(), consume(), run.wait())
    assert first == second == result.events
    assert result.status == "stopped"


async def test_abort_before_start_does_not_send_prompt(
    step_sdk: AutohandSDK, tmp_path: Path
) -> None:
    """An unstarted run can be cancelled without touching the CLI turn state."""
    run = Agent.from_sdk(step_sdk).send("unused")
    await run.abort()
    assert (await run.wait()).status == "aborted"
    assert not any(request["method"] == "autohand.prompt" for request in requests(tmp_path))


async def test_predicate_error_stops_then_surfaces(step_sdk: AutohandSDK, tmp_path: Path) -> None:
    """Settle the paused harness before surfacing a host callback failure."""

    def fail(_context: StopConditionContext) -> bool:
        raise ValueError("predicate failed")

    agent = Agent.from_sdk(step_sdk)
    run = agent.send("inspect", stop_when=fail)
    for _ in range(2):
        with pytest.raises(ValueError, match="predicate failed"):
            await asyncio.wait_for(run.wait(), 3)
    assert (await agent.run("continue")).status == "completed"
    assert any(request["params"] == {"stepId": "1", "stop": True} for request in requests(tmp_path))


async def test_abort_pending_condition_is_scoped(step_sdk: AutohandSDK, tmp_path: Path) -> None:
    """Cancelling a queued run leaves the active run and its pending predicate intact."""
    entered = asyncio.Event()
    cancelled = asyncio.Event()

    async def pending(_context: StopConditionContext) -> bool:
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
        return False

    agent = Agent.from_sdk(step_sdk)
    active = agent.send("inspect", stop_when=pending)
    active_wait = asyncio.create_task(active.wait())
    await asyncio.wait_for(entered.wait(), 3)
    queued = agent.send("queued")
    queued_wait = asyncio.create_task(queued.wait())
    await asyncio.sleep(0)
    await queued.abort()
    assert (await queued_wait).status == "aborted"
    assert not cancelled.is_set()
    assert not any(request["method"] == "autohand.abort" for request in requests(tmp_path))
    await asyncio.gather(active.abort(), active.abort())
    assert (await active_wait).status == "aborted"
    assert cancelled.is_set()
    assert (await agent.run("continue")).status == "completed"


async def test_external_abort_cancels_pending_predicate(step_sdk: AutohandSDK) -> None:
    """A CLI terminal event must settle even when a host callback is still awaiting input."""
    entered = asyncio.Event()

    async def pending(_context: StopConditionContext) -> bool:
        entered.set()
        await asyncio.Event().wait()
        return False

    run = Agent.from_sdk(step_sdk).send("inspect", stop_when=pending)
    task = asyncio.create_task(run.wait())
    await asyncio.wait_for(entered.wait(), 3)
    await step_sdk.abort()
    try:
        assert (await asyncio.wait_for(asyncio.shield(task), 0.5)).status == "aborted"
    finally:
        await run.abort()


async def test_early_stream_close_aborts_before_return(
    step_sdk: AutohandSDK, tmp_path: Path
) -> None:
    """The convenience iterator owns its run and settles it when explicitly closed."""
    stream = Agent.from_sdk(step_sdk).stream("inspect", stop_when=is_step_count(10))
    assert (await anext(stream))["type"] == "turn_start"
    await stream.aclose()
    assert any(request["method"] == "autohand.abort" for request in requests(tmp_path))
    assert (await Agent.from_sdk(step_sdk).run("continue")).status == "completed"


@pytest.mark.parametrize("message", ["malformed", "rejected", "invalid-response"])
async def test_protocol_failure_settles_turn(step_sdk: AutohandSDK, message: str) -> None:
    """Do not strand the harness after malformed events or rejected decisions."""
    agent = Agent.from_sdk(step_sdk)
    with pytest.raises((TransportError, ValidationError)):
        await asyncio.wait_for(agent.run(message, stop_when=is_step_count(1)), 3)
    assert (await agent.run("continue")).status == "completed"


async def test_exit_after_ack_is_failure(step_sdk: AutohandSDK) -> None:
    """An acknowledged prompt is not completed when the process exits mid-turn."""
    with pytest.raises(TransportError):
        await asyncio.wait_for(Agent.from_sdk(step_sdk).run("exit"), 3)
