#!/usr/bin/env python3
"""Deterministic JSON-RPC fixture used by the startup benchmark."""

from __future__ import annotations

import json
import sys

for raw_line in sys.stdin:
    request = json.loads(raw_line)
    result = {"status": "idle"} if request.get("method") == "autohand.getState" else {}
    print(
        json.dumps({"jsonrpc": "2.0", "id": request.get("id"), "result": result}),
        flush=True,
    )
