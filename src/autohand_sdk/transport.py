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
from contextlib import suppress
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
TerminationCallback = Callable[[BaseException], None]


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
    auto_commit: bool | None = None
    bare: bool | None = None
    idle_logout: bool | None = None
    model: str | None = None
    temperature: float | None = None
    max_iterations: int | None = None
    max_runtime: int | None = None
    max_cost: float | None = None
    sys_prompt: str | None = None
    system_prompt_file: str | None = None
    append_sys_prompt: str | None = None
    append_system_prompt_file: str | None = None
    display_language: str | None = None
    mcp_config: str | None = None
    agents: str | None = None
    plugin_dir: str | None = None
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
    fork: str | None = None
    session_path: str | None = None
    auto_save_interval: int | None = None
    context_compact: bool | None = None
    max_tokens: int | None = None
    compression_threshold: float | None = None
    summarization_threshold: float | None = None
    agents_md_enable: bool | None = None
    agents_md_create: bool | None = None
    agents_md_path: str | None = None
    agents_md_auto_update: bool | None = None
    copy_skill_files: bool = True
    provider: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    autohand_ai_plan: str | None = None
    env_vars: dict[str, str] = field(default_factory=dict)


class Transport:
    """Transport for communicating with the Autohand CLI subprocess."""

    def __init__(self, options: TransportOptions | None = None) -> None:
        self.options = options or TransportOptions()
        self._process: asyncio.subprocess.Process | None = None
        self._callbacks: dict[int, asyncio.Future[JsonDict]] = {}
        self._notification_callbacks: dict[str, list[NotificationCallback]] = defaultdict(list)
        self._termination_callbacks: list[TerminationCallback] = []
        self._request_id = 0
        self._running = False
        self._stdout_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._stderr_lines: list[str] = []
        self._lifecycle_lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()
        self._retirement_tasks: set[asyncio.Task[None]] = set()

    async def start(self) -> None:
        """Start the CLI subprocess."""
        async with self._lifecycle_lock:
            if self.is_running():
                return
            if self._process is not None:
                await self._stop_process(
                    self._process,
                    TransportError("Retiring an unusable transport generation"),
                )
            await self._start_process()

    async def _start_process(self) -> None:
        """Start one process while the lifecycle lock is held."""
        cli_path = self.options.cli_path or self._detect_cli_binary()
        cwd = self.options.cwd or str(Path.cwd())

        if self.options.copy_skill_files and (self.options.skills or self.options.skill_files):
            await self._copy_skill_files(cwd)

        args = [cli_path, "--mode", "rpc"]
        if self.options.bare:
            args.append("--bare")
        if self.options.unrestricted:
            args.append("--unrestricted")
        if self.options.auto_mode:
            args.append("--auto-mode")
        if self.options.auto_skill:
            args.append("--auto-skill")
        if self.options.auto_commit:
            args.append("-c")
        if self.options.idle_logout is False:
            args.append("--no-idle-logout")
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
        if self.options.fork:
            args.extend(["--fork", self.options.fork])
        if self.options.session_path:
            args.extend(["--session-path", self.options.session_path])
        if self.options.auto_save_interval is not None:
            args.extend(["--auto-save-interval", str(self.options.auto_save_interval)])
        if self.options.agents_md_enable is False:
            args.append("--no-agents-md")
        elif self.options.agents_md_enable is True:
            args.append("--agents-md")
        if self.options.agents_md_create:
            args.append("--agents-md-create")
        if self.options.agents_md_path:
            args.extend(["--agents-md-path", self.options.agents_md_path])
        if self.options.agents_md_auto_update:
            args.append("--agents-md-auto-update")
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
        if self.options.display_language:
            args.extend(["--display-language", self.options.display_language])
        if self.options.sys_prompt:
            args.extend(["--sys-prompt", self.options.sys_prompt])
        if self.options.system_prompt_file:
            args.extend(["--system-prompt-file", self.options.system_prompt_file])
        if self.options.append_sys_prompt:
            args.extend(["--append-sys-prompt", self.options.append_sys_prompt])
        if self.options.append_system_prompt_file:
            args.extend(["--append-system-prompt-file", self.options.append_system_prompt_file])
        if self.options.mcp_config:
            args.extend(["--mcp-config", self.options.mcp_config])
        if self.options.agents:
            args.extend(["--agents", self.options.agents])
        if self.options.plugin_dir:
            args.extend(["--plugin-dir", self.options.plugin_dir])
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
        if self.options.provider == "autohandai":
            env["AUTOHAND_AI_PLAN"] = self.options.autohand_ai_plan or "cloud"
            if self.options.api_key:
                env["AUTOHAND_AI_API_KEY"] = self.options.api_key
            if self.options.base_url:
                env["AUTOHAND_AI_BASE_URL"] = self.options.base_url
        env.update(self.options.env_vars)

        self._stderr_lines.clear()
        process = await asyncio.create_subprocess_exec(
            *args,
            cwd=cwd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        self._process = process
        self._running = True
        self._stdout_task = asyncio.create_task(self._read_stdout(process))
        self._stderr_task = asyncio.create_task(self._read_stderr(process))
        await asyncio.sleep(0)
        if process.returncode is not None:
            returncode = process.returncode
            stderr_tail = self._format_stderr_tail()
            await self._stop_process(
                process,
                TransportError(
                    f"CLI process exited during startup with code {returncode}{stderr_tail}"
                ),
            )
            raise TransportError(
                f"CLI process exited during startup with code {returncode}{stderr_tail}"
            )

    async def stop(self) -> None:
        """Stop the CLI subprocess."""
        async with self._lifecycle_lock:
            if self._process is None:
                return
            await self._stop_process(
                self._process,
                TransportError("Transport stopped before receiving a response"),
            )

    async def _stop_process(
        self,
        process: asyncio.subprocess.Process,
        error: BaseException,
    ) -> None:
        """Stop one captured process without mutating a newer generation."""
        if self._process is not process:
            return
        self._running = False
        self._fail_pending_requests(error)
        if process.stdin:
            with suppress(OSError, RuntimeError):
                process.stdin.close()

        current_task = asyncio.current_task()
        reader_tasks = [
            task
            for task in (self._stdout_task, self._stderr_task)
            if task is not None and task is not current_task
        ]
        for task in reader_tasks:
            if not task.done():
                task.cancel()
        if reader_tasks:
            await asyncio.gather(*reader_tasks, return_exceptions=True)

        async with self._write_lock:
            if process.stdin:
                with suppress(OSError, RuntimeError):
                    await process.stdin.wait_closed()
        if process.returncode is None:
            try:
                process.terminate()
                await asyncio.wait_for(process.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                with suppress(ProcessLookupError):
                    process.kill()
                with suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(process.wait(), timeout=1.0)
            except ProcessLookupError:
                pass
        self._process = None
        self._stdout_task = None
        self._stderr_task = None

    async def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        """Send a JSON-RPC request and wait for response."""
        process = self._process
        if not process or not process.stdin or not self._running:
            raise TransportNotStartedError("Transport not started")
        if process.returncode is not None:
            raise TransportError(f"Transport process exited with code {process.returncode}")

        self._request_id += 1
        request_id = self._request_id
        request = {"jsonrpc": "2.0", "method": method, "params": params or {}, "id": request_id}

        future: asyncio.Future[JsonDict] = asyncio.get_running_loop().create_future()
        self._callbacks[request_id] = future
        data = json.dumps(request) + "\n"
        try:
            try:
                async with self._write_lock:
                    if self._process is not process or not self._running or not process.stdin:
                        raise TransportNotStartedError("Transport generation is no longer active")
                    process.stdin.write(data.encode())
                    await process.stdin.drain()
            except (BrokenPipeError, ConnectionResetError, RuntimeError) as exc:
                raise TransportError(
                    f"Failed to write RPC request {method} to CLI stdin{self._format_stderr_tail()}"
                ) from exc

            response = await asyncio.wait_for(future, timeout=self.options.timeout / 1000)
        except asyncio.TimeoutError:
            raise RequestTimeoutError(f"Request timeout: {method}") from None
        finally:
            self._callbacks.pop(request_id, None)
            if not future.done():
                future.cancel()

        if "error" in response:
            error = response["error"]
            raise RPCError(
                error.get("message", f"RPC request failed: {method}"),
                code=error.get("code"),
                data=error.get("data"),
            )
        return response.get("result")

    def on_notification(self, method: str, callback: NotificationCallback) -> Callable[[], None]:
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

    def on_termination(self, callback: TerminationCallback) -> Callable[[], None]:
        """Register a callback for an unexpected stdout failure or closure."""
        self._termination_callbacks.append(callback)

        def unsubscribe() -> None:
            with suppress(ValueError):
                self._termination_callbacks.remove(callback)

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

        # Prefer the standard executable installed by the Autohand CLI, then
        # retain compatibility with older platform-specific installations.
        for candidate in ("autohand", binary_name):
            cli_path = shutil.which(candidate)
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

    async def _read_stdout(self, process: asyncio.subprocess.Process | None = None) -> None:
        """Read JSON-RPC responses and notifications from stdout."""
        process = process or self._process
        if not process or not process.stdout:
            return

        while self._process is process and self._running:
            try:
                line = await process.stdout.readline()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if self._process is process:
                    self._running = False
                    error = TransportError(f"Failed reading CLI stdout: {exc}")
                    self._fail_pending_requests(error)
                    self._notify_termination(error)
                    self._schedule_retirement(process, error)
                break

            if not line:
                if self._process is process:
                    self._running = False
                    error = TransportError("CLI stdout closed")
                    self._fail_pending_requests(error)
                    self._notify_termination(error)
                    self._schedule_retirement(process, error)
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

    def _notify_termination(self, error: BaseException) -> None:
        """Notify lifecycle consumers without letting callback errors escape the reader."""
        for callback in tuple(self._termination_callbacks):
            try:
                callback(error)
            except Exception:
                logger.exception("Unhandled exception in transport termination callback")

    async def _read_stderr(self, process: asyncio.subprocess.Process | None = None) -> None:
        """Read stderr from the process."""
        process = process or self._process
        if not process or not process.stderr:
            return
        while self._process is process and self._running:
            try:
                line = await process.stderr.readline()
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
        return self._running and self._process is not None and self._process.returncode is None

    async def _retire_generation(
        self,
        process: asyncio.subprocess.Process,
        error: BaseException,
    ) -> None:
        async with self._lifecycle_lock:
            await self._stop_process(process, error)

    def _schedule_retirement(
        self,
        process: asyncio.subprocess.Process,
        error: BaseException,
    ) -> None:
        """Keep unexpected-exit cleanup alive until it releases the child."""
        task = asyncio.create_task(self._retire_generation(process, error))
        self._retirement_tasks.add(task)
        task.add_done_callback(self._finish_retirement)

    def _finish_retirement(self, task: asyncio.Task[None]) -> None:
        """Observe background cleanup failures and release the strong task reference."""
        self._retirement_tasks.discard(task)
        try:
            task.result()
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("Unexpected failure while retiring a CLI process generation")
