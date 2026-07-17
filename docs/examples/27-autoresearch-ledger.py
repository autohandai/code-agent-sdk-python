"""Run and inspect a replayable autoresearch session.

Usage:
    AUTOHAND_TARGET_REPO=/path/to/project uv run python docs/examples/27-autoresearch-ledger.py

The target must be a clean Git repository with at least one commit. This example
permits autonomous local edits but never asks the agent to push them.
"""

from __future__ import annotations

import asyncio
import os

from autohand_sdk import AutohandSDK, parse_sdk_event


def require_success(operation: str, success: bool, error: str | None) -> None:
    """Raise a useful error for an unsuccessful autoresearch operation."""
    if not success:
        raise RuntimeError(f"{operation} failed: {error or 'unknown error'}")


async def main() -> None:
    """Start autoresearch, execute its instruction, and inspect the ledger."""
    target = os.environ.get("AUTOHAND_TARGET_REPO", ".")
    cli_path = os.environ.get("AUTOHAND_CLI_PATH")
    model = os.environ.get("AUTOHAND_MODEL")
    api_key = os.environ.get("AUTOHAND_AI_API_KEY")

    async with AutohandSDK(
        cwd=target,
        cli_path=cli_path,
        model=model,
        api_key=api_key,
        unrestricted=True,
        timeout=600_000,
    ) as sdk:
        started = await sdk.start_autoresearch(
            objective="Reduce test runtime without changing behavior",
            max_iterations=10,
            timeout_ms=600_000,
            metric_name="test_ms",
            metric_unit="ms",
            direction="lower",
            measure_script=(
                "set -euo pipefail\n"
                "start=$(python -c 'import time; print(time.time_ns() // 1000000)')\n"
                "uv run pytest\n"
                "end=$(python -c 'import time; print(time.time_ns() // 1000000)')\n"
                "printf 'METRIC test_ms=%s\\n' \"$((end - start))\"\n"
            ),
            checks_command="uv run mypy src && uv run ruff check .",
            files_in_scope=["src", "tests"],
        )
        require_success("start_autoresearch", started.success, started.error)
        if not started.instruction:
            raise RuntimeError("start_autoresearch returned no loop instruction")

        async for raw_event in sdk.stream_prompt(started.instruction):
            event = parse_sdk_event(raw_event)
            if not isinstance(event, dict) and event.type == "autoresearch":
                if hasattr(event, "operation"):
                    print(f"[ledger:{event.phase}] {event.operation}")
                else:
                    print(f"[autoresearch:{event.phase}] {event.status_text}")

        status = await sdk.get_autoresearch_status()
        require_success("get_autoresearch_status", status.success, status.error)
        history = await sdk.get_autoresearch_history()
        require_success("get_autoresearch_history", history.success, history.error)
        pareto = await sdk.get_autoresearch_pareto()
        require_success("get_autoresearch_pareto", pareto.success, pareto.error)

        print(f"runs logged: {status.runs_logged}")
        print(f"attempts: {len(history.attempts)}")
        print(f"pareto attempts: {', '.join(pareto.attempt_ids) or 'none'}")

        preview = await sdk.prune_autoresearch(dry_run=True)
        require_success("prune_autoresearch", preview.success, preview.error)
        print(f"prune preview: {preview.bytes_freed} bytes")

        if status.active:
            stopped = await sdk.stop_autoresearch()
            require_success("stop_autoresearch", stopped.success, stopped.error)


if __name__ == "__main__":
    asyncio.run(main())
