#!/usr/bin/env python3
"""Gate wrapper-controlled SDK startup latency at p95 below 50 ms."""

from __future__ import annotations

import asyncio
import json
import math
import os
import statistics
import subprocess
import sys
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

WARMUPS = 5
SAMPLES = 50
BUDGET_MS = 50.0
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src"
FIXTURE_CLI = ROOT / "benchmarks" / "fake_cli.py"


def summarize(values: list[float]) -> dict[str, float | int | bool]:
    """Return deterministic nearest-rank latency statistics."""
    ordered = sorted(values)
    p95_index = math.ceil(0.95 * len(ordered)) - 1
    p95_ms = round(ordered[p95_index], 3)
    return {
        "samples": len(ordered),
        "medianMs": round(statistics.median(ordered), 3),
        "p95Ms": p95_ms,
        "maxMs": round(ordered[-1], 3),
        "passed": p95_ms < BUDGET_MS,
        "minMs": round(ordered[0], 3),
        "meanMs": round(statistics.fmean(ordered), 3),
    }


def public_import_sample() -> float:
    """Time only the import inside a fresh interpreter process."""
    environment = dict(os.environ)
    existing_path = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        f"{SOURCE}{os.pathsep}{existing_path}" if existing_path else str(SOURCE)
    )
    code = (
        "import time; "
        "started=time.perf_counter_ns(); "
        "import autohand_sdk; "
        "print((time.perf_counter_ns()-started)/1_000_000)"
    )
    output = subprocess.check_output(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=environment,
        text=True,
    )
    return float(output.strip())


async def sdk_start_sample() -> float:
    """Time the public SDK start call through its successful readiness RPC."""
    from autohand_sdk import AutohandSDK, SDKConfig  # noqa: PLC0415

    sdk = AutohandSDK(SDKConfig(cli_path=str(FIXTURE_CLI), cwd=str(ROOT), timeout=2_000))
    started = time.perf_counter_ns()
    try:
        await sdk.start()
        return (time.perf_counter_ns() - started) / 1_000_000
    finally:
        await sdk.close()


async def fixture_rpc_sample() -> float:
    """Time fixture spawn through the first successful getState response."""
    from autohand_sdk.transport import Transport, TransportOptions  # noqa: PLC0415

    transport = Transport(TransportOptions(cli_path=str(FIXTURE_CLI), cwd=str(ROOT), timeout=2_000))
    started = time.perf_counter_ns()
    try:
        await transport.start()
        await transport.request("autohand.getState", {})
        return (time.perf_counter_ns() - started) / 1_000_000
    finally:
        await transport.stop()


def collect_sync(sample: Callable[[], float]) -> list[float]:
    """Run the fixed warmup and measured sample counts."""
    for _ in range(WARMUPS):
        sample()
    return [sample() for _ in range(SAMPLES)]


async def collect_async(sample: Callable[[], Awaitable[float]]) -> list[float]:
    """Run the fixed warmup and measured sample counts asynchronously."""
    for _ in range(WARMUPS):
        await sample()
    return [await sample() for _ in range(SAMPLES)]


async def main() -> int:
    """Measure all wrapper-controlled metrics and enforce the p95 gate."""
    metrics = {
        "publicImportMs": summarize(collect_sync(public_import_sample)),
        "sdkStartReturnMs": summarize(await collect_async(sdk_start_sample)),
        "fixtureSpawnToFirstRpcMs": summarize(await collect_async(fixture_rpc_sample)),
    }
    passed = all(bool(stats["passed"]) for stats in metrics.values())
    result = {
        "language": "python",
        "budgetMs": BUDGET_MS,
        "metrics": metrics,
        "passed": passed,
        "warmups": WARMUPS,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    failures = [name for name, stats in metrics.items() if not stats["passed"]]
    if failures:
        print(f"startup p95 gate failed: {', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
