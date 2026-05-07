"""Transport layer for CLI subprocess communication."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import shutil
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from autohand_sdk.errors import (
    RequestTimeoutError,
    RPCError,
    TransportError,
    TransportNotStartedError,
)

logger = logging.getLogger(__name__)

JsonDict = dict[str, Any]
NotificationCallback = Callable[[JsonDict], None]


@dataclass
class TransportOptions:
    """Configuration options for the Transport layer."""
    cwd: str | None = None
    cli_path: str | None = None
    debug: bool = False
    timeout: int = 300000
    auto_mode: bool | None = None
    unrestricted: bool | None = None
    auto_skill: bool | None = None
    model: str | None = None
    temperature: float | None = None
    max_iterations: int | None = None
    max_runtime: int | None = None
    max_cost: float | None = None
    sys_prompt: str | None = None
    append_sys_prompt: str | None = None
    yolo: str | None = None
    yolo_timeout: int | None = None
    add_dir: list[str] = field(default_factory=list)
    extra_args: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    skill_files: list[str] = field(default_factory=list)
    skill_sources: list[str] = field(default_factory=list)
    install_missing_skills: bool | None = None
    permission_mode: str | None = None
    permission_allow_list: list[str] = field(default_factory=list)
    permission_deny_list: list[str] = field(default_factory=list)
    persist_session: bool | None = None
    session_id: str | None = None
    resume: bool | None = None
    continue_session: bool | None = None
    session_path: str | None = None
    auto_save_interval: int | None = None
    context_compact: bool | None = None
    max_tokens: int | None = None
    compression_threshold: float | None = None
    summarization_threshold: float | None = None
    copy_skill_files: bool = True
    env_vars: dict[str, str] = field(default_factory=dict)


class Transport:
    """Transport for communicating with the Autohand CLI subprocess."""

    def __init__(self, options: TransportOptions | None = None) -> None:
        self.options = options or TransportOptions()
        self._process: asyncio.subprocess.Process | None = None
        self._callbacks: dict[int, asyncio.Future[JsonDict]] = {}
        self._notification_callbacks: dict[str, list[NotificationCallback]] = defaultdict(list)
        self._request_id = 0
        self._running = False
        self._stdout_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._stderr_lines: list[str] = []

    async def start(self) -> None:
        """Start the CLI subprocess."""
        if self.is_running():
            return

        cli_path = self.options.cli_path or self._detect_cli_binary()
        cwd = self.options.cwd or str(Path.cwd())

        if self.options.copy_skill_files and (self.options.skills or self.options.skill_files):
            await self._copy_skill_files(cwd)

        args = [cli_path, "--mode", "rpc"]
        if self.options.unrestricted:
            args.append("--unrestricted")
        if self.options.auto_mode:
            args.append("--auto-mode")
        if self.options.auto_skill:
            args.append("--auto-skill")
        if self.options.context_compact is False:
            args.append("--no-context-compact")
        elif self.options.context_compact is True:
            args.append("--context-compact")
        if self.options.persist_session:
            args.append("--persist-session")
        if self.options.session_id:
            args.extend(["--session-id", self.options.session_id])
        if self.options.resume:
            args.append("--resume")
        if self.options.continue_session:
            args.append("--continue")
        if self.options.session_path:
            args.extend(["--session-path", self.options.session_path])
        if self.options.auto_save_interval is not None:
            args.extend(["--auto-save-interval", str(self.options.auto_save_interval)])
        if self.options.max_tokens is not None:
            args.extend(["--max-tokens", str(self.options.max_tokens)])
        if self.options.compression_threshold is not None:
            args.extend(["--compression-threshold", str(self.options.compression_threshold)])
        if self.options.summarization_threshold is not None:
            args.extend(["--summarization-threshold", str(self.options.summarization_threshold)])
        if self.options.skills:
            args.extend(["--skills", ",".join(self.options.skills)])
        if self.options.skill_sources:
            args.extend(["--skill-sources", ",".join(self.options.skill_sources)])
        if self.options.install_missing_skills:
            args.append("--install-missing-skills")
        if self.options.permission_mode:
            args.extend(["--permission-mode", self.options.permission_mode])
        if self.options.permission_allow_list:
            args.extend(["--permission-allow-list", ",".join(self.options.permission_allow_list)])
        if self.options.permission_deny_list:
            args.extend(["--permission-deny-list", ",".join(self.options.permission_deny_list)])
        if self.options.max_iterations is not None:
            args.extend(["--max-iterations", str(self.options.max_iterations)])
        if self.options.max_runtime is not None:
            args.extend(["--max-runtime", str(self.options.max_runtime)])
        if self.options.max_cost is not None:
            args.extend(["--max-cost", str(self.options.max_cost)])
        if self.options.sys_prompt:
            args.extend(["--sys-prompt", self.options.sys_prompt])
        if self.options.append_sys_prompt:
            args.extend(["--append-sys-prompt", self.options.append_sys_prompt])
        if self.options.model:
            args.extend(["--model", self.options.model])
        if self.options.temperature is not None:
            args.extend(["--temperature", str(self.options.temperature)])
        if self.options.yolo:
            args.extend(["--yolo", self.options.yolo])
        if self.options.yolo_timeout is not None:
            args.extend(["--yolo-timeout", str(self.options.yolo_timeout)])
        for directory in self.options.add_dir:
            args.extend(["--add-dir", directory])
        args.extend(self.options.extra_args)

        env = dict(os.environ)
        env["AUTOHAND_STREAM_TOOL_OUTPUT"] = "1"
        env.update(self.options.env_vars)

        self._process = await asyncio.create_subprocess_exec(
            *args,
            cwd=cwd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        self._running = True
        self._stdout_task = asyncio.create_task(self._read_stdout())
        self._stderr_task = asyncio.create_task(self._read_stderr())
        await asyncio.sleep(0)
        if self._process.returncode is not None:
            returncode = self._process.returncode
            stderr_tail = self._format_stderr_tail()
            await self.stop()
            raise TransportError(
                f"CLI process exited during startup with code {returncode}"
                f"{stderr_tail}"
            )

    async def stop(self) -> None:
        """Stop the CLI subprocess."""
        if not self._process:
            return
        self._running = False

        for task in (self._stdout_task, self._stderr_task):
            if task and not task.done():
                task.cancel()

        if self._process.stdin:
            self._process.stdin.close()
        if self._process.returncode is None:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
        self._process = None
        self._stdout_task = None
        self._stderr_task = None
        self._fail_pending_requests(TransportError("Transport stopped before receiving a response"))

    async def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        """Send a JSON-RPC request and wait for response."""
        if not self._process or not self._process.stdin:
            raise TransportNotStartedError("Transport not started")
        if self._process.returncode is not None:
            raise TransportError(f"Transport process exited with code {self._process.returncode}")

        self._request_id += 1
        request_id = self._request_id
        request = {"jsonrpc": "2.0", "method": method, "params": params or {}, "id": request_id}

        future: asyncio.Future[JsonDict] = asyncio.get_running_loop().create_future()
        self._callbacks[request_id] = future
        data = json.dumps(request) + "\n"
        try:
            self._process.stdin.write(data.encode())
            await self._process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError, RuntimeError) as exc:
            self._callbacks.pop(request_id, None)
            raise TransportError(
                f"Failed to write RPC request {method} to CLI stdin"
                f"{self._format_stderr_tail()}"
            ) from exc

        try:
            response = await asyncio.wait_for(future, timeout=self.options.timeout / 1000)
        except asyncio.TimeoutError:
            raise RequestTimeoutError(f"Request timeout: {method}") from None
        finally:
            self._callbacks.pop(request_id, None)

        if "error" in response:
            error = response["error"]
            raise RPCError(
                error.get("message", f"RPC request failed: {method}"),
                code=error.get("code"),
                data=error.get("data"),
            )
        return response.get("result")

    def on_notification(
        self, method: str, callback: NotificationCallback
    ) -> Callable[[], None]:
        """Register a notification callback.

        Args:
            method: JSON-RPC notification method. Use "*" to receive all notifications.
            callback: Function called with the notification params plus ``_method``.

        Returns:
            A function that unregisters the callback.
        """
        callbacks = self._notification_callbacks[method]
        callbacks.append(callback)

        def unsubscribe() -> None:
            try:
                callbacks.remove(callback)
            except ValueError:
                return

        return unsubscribe

    def _detect_cli_binary(self) -> str:
        """Detect the CLI binary for the current platform."""
        system = platform.system().lower()
        machine = platform.machine().lower()

        binary_map = {
            ("darwin", "arm64"): "autohand-macos-arm64",
            ("darwin", "x86_64"): "autohand-macos-x64",
            ("linux", "arm64"): "autohand-linux-arm64",
            ("linux", "x86_64"): "autohand-linux-x64",
            ("windows", "amd64"): "autohand-windows-x64.exe",
        }

        binary_name = binary_map.get((system, machine))
        if not binary_name:
            raise RuntimeError(f"Unsupported platform: {system}/{machine}")

        # Try package path first
        package_path = Path(__file__).parent.parent.parent / "cli" / binary_name
        if package_path.exists():
            return str(package_path)

        # Fall back to PATH
        cli_path = shutil.which(binary_name.replace(".exe", ""))
        if cli_path:
            return cli_path

        return binary_name

    async def _copy_skill_files(self, cwd: str) -> None:
        """Copy skill files to ~/.autohand/skills/."""
        if not self.options.copy_skill_files:
            return

        home_dir = Path.home()
        skills_dir = home_dir / ".autohand" / "skills"

        skill_files = [
            skill
            for skill in [*self.options.skill_files, *self.options.skills]
            if "/" in skill or "\\" in skill or skill.endswith((".md", ".MD"))
        ]

        for skill in skill_files:
            if "/" not in skill and "\\" not in skill and not skill.endswith((".md", ".MD")):
                continue

            raw_path = Path(skill).expanduser()
            src_path = raw_path if raw_path.is_absolute() else Path(cwd) / raw_path
            if not src_path.exists():
                continue

            parts = [p for p in raw_path.parts if p and p not in (".", "..")]
            name = parts[-1] if parts else "custom-skill"
            if name == "SKILL.md" and len(parts) > 1:
                name = parts[-2]
            name = name.replace(".md", "").replace(".MD", "")

            dest_dir = skills_dir / name
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_path = dest_dir / "SKILL.md"

            content = src_path.read_text()
            dest_path.write_text(content)

    async def _read_stdout(self) -> None:
        """Read JSON-RPC responses and notifications from stdout."""
        if not self._process or not self._process.stdout:
            return

        while self._running:
            try:
                line = await self._process.stdout.readline()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._fail_pending_requests(TransportError(f"Failed reading CLI stdout: {exc}"))
                break

            if not line:
                self._fail_pending_requests(TransportError("CLI stdout closed"))
                break

            self._handle_stdout_line(line)

    def _handle_stdout_line(self, line: bytes) -> None:
        """Parse and dispatch one JSON-RPC line from stdout."""
        try:
            message = json.loads(line.decode())
        except json.JSONDecodeError:
            logger.debug("Ignoring non-JSON RPC stdout line: %r", line)
            return

        if isinstance(message, list):
            for item in message:
                if isinstance(item, dict):
                    self._handle_rpc_message(item)
            return

        if isinstance(message, dict):
            self._handle_rpc_message(message)

    def _handle_rpc_message(self, message: JsonDict) -> None:
        """Dispatch a decoded JSON-RPC message."""
        if "id" in message:
            request_id = message["id"]
            future = self._callbacks.get(request_id)
            if future and not future.done():
                future.set_result(message)
            return

        method = message.get("method")
        if not isinstance(method, str):
            return

        params = message.get("params")
        if not isinstance(params, dict):
            params = {"value": params} if params is not None else {}
        params = {**params, "_method": method}

        callbacks = [
            *self._notification_callbacks.get(method, []),
            *self._notification_callbacks.get("*", []),
        ]
        for callback in callbacks:
            try:
                callback(params)
            except Exception:
                logger.exception("Unhandled exception in notification callback for %s", method)

    def _fail_pending_requests(self, error: BaseException) -> None:
        """Fail all outstanding request futures."""
        for future in self._callbacks.values():
            if not future.done():
                future.set_exception(error)
        self._callbacks.clear()

    async def _read_stderr(self) -> None:
        """Read stderr from the process."""
        if not self._process or not self._process.stderr:
            return
        while self._running:
            try:
                line = await self._process.stderr.readline()
                if not line:
                    break
                text = line.decode(errors="replace").strip()
                if text:
                    self._stderr_lines.append(text)
                    self._stderr_lines = self._stderr_lines[-50:]
                if self.options.debug:
                    logger.debug("[CLI stderr] %s", text)
            except asyncio.CancelledError:
                raise
            except Exception:
                break

    @property
    def stderr_tail(self) -> str:
        """Return recently captured CLI stderr lines."""
        return "\n".join(self._stderr_lines)

    def _format_stderr_tail(self) -> str:
        """Format captured stderr for exception messages."""
        stderr = self.stderr_tail
        return f":\n{stderr}" if stderr else ""

    def is_running(self) -> bool:
        """Check if the process is running."""
        return self._process is not None and self._process.returncode is None
