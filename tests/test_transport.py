"""Tests for the Transport layer."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from autohand_sdk.errors import RequestTimeoutError, RPCError
from autohand_sdk.transport import Transport, TransportOptions


class TestTransportOptions:
    """Tests for TransportOptions dataclass."""

    def test_default_options(self) -> None:
        opts = TransportOptions()
        assert opts.cwd is None
        assert opts.cli_path is None
        assert opts.debug is False
        assert opts.timeout == 300000
        assert opts.skills == []
        assert opts.env_vars == {}

    def test_custom_options(self) -> None:
        opts = TransportOptions(
            cwd="/test",
            cli_path="/usr/bin/autohand",
            debug=True,
            skills=["typescript"],
            env_vars={"AUTOHAND_DEBUG": "1"},
        )
        assert opts.cwd == "/test"
        assert opts.cli_path == "/usr/bin/autohand"
        assert opts.debug is True
        assert opts.skills == ["typescript"]
        assert opts.env_vars == {"AUTOHAND_DEBUG": "1"}


class TestTransportInitialization:
    """Tests for Transport initialization."""

    def test_default_transport(self) -> None:
        transport = Transport()
        assert transport.options.debug is False
        assert transport._process is None

    def test_transport_with_options(self) -> None:
        opts = TransportOptions(debug=True)
        transport = Transport(opts)
        assert transport.options.debug is True


class TestTransportLifecycle:
    """Tests for Transport start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_detects_cli(self, tmp_path: Path) -> None:
        # Create mock binary
        cli_dir = tmp_path / "cli"
        cli_dir.mkdir()
        binary_name = "autohand-macos-arm64" if sys.platform == "darwin" else "autohand-linux-x64"
        binary = cli_dir / binary_name
        binary.write_text("#!/bin/bash\necho '{}'", encoding="utf-8")
        binary.chmod(0o755)

        with patch.object(Path, "parent", new_callable=MagicMock) as mock_parent:
            mock_parent.parent.parent = cli_dir
            # Just test detection logic separately
            pass

    @pytest.mark.asyncio
    async def test_stop_without_start(self) -> None:
        transport = Transport()
        # Should not raise
        await transport.stop()
        assert transport._process is None

    @pytest.mark.asyncio
    async def test_is_running_not_started(self) -> None:
        transport = Transport()
        assert transport.is_running() is False


class TestTransportSkillCopying:
    """Tests for skill file copying."""

    @pytest.mark.asyncio
    async def test_copy_skill_files_with_name_skips(self, tmp_path: Path, monkeypatch) -> None:
        transport = Transport(TransportOptions(skills=["typescript", "react"]))
        home_dir = tmp_path / "home"
        monkeypatch.setenv("HOME", str(home_dir))

        await transport._copy_skill_files(str(tmp_path))

        skills_dir = home_dir / ".autohand" / "skills"
        assert not skills_dir.exists()  # Should not create for non-file skills

    @pytest.mark.asyncio
    async def test_copy_skill_files_with_path(self, tmp_path: Path, monkeypatch) -> None:
        # Create a skill file
        skills_dir = tmp_path / "skills" / "custom"
        skills_dir.mkdir(parents=True)
        skill_file = skills_dir / "SKILL.md"
        skill_file.write_text("# Custom Skill")

        transport = Transport(
            TransportOptions(skills=["typescript", "./skills/custom/SKILL.md"])
        )
        home_dir = tmp_path / "home"
        monkeypatch.setenv("HOME", str(home_dir))

        await transport._copy_skill_files(str(tmp_path))

        dest_dir = home_dir / ".autohand" / "skills" / "custom"
        dest_file = dest_dir / "SKILL.md"
        assert dest_dir.exists()
        assert dest_file.exists()
        assert dest_file.read_text() == "# Custom Skill"

    @pytest.mark.asyncio
    async def test_copy_skill_files_nonexistent_path(self, tmp_path: Path, monkeypatch) -> None:
        transport = Transport(
            TransportOptions(skills=["./skills/nonexistent/SKILL.md"])
        )
        home_dir = tmp_path / "home"
        monkeypatch.setenv("HOME", str(home_dir))

        # Should not raise
        await transport._copy_skill_files(str(tmp_path))

        skills_dir = home_dir / ".autohand" / "skills"
        assert not skills_dir.exists()

    @pytest.mark.asyncio
    async def test_copy_skill_files_with_simple_md(self, tmp_path: Path, monkeypatch) -> None:
        # Create a simple .md file
        skill_file = tmp_path / "custom-skill.md"
        skill_file.write_text("# Custom Skill")

        transport = Transport(TransportOptions(skills=["./custom-skill.md"]))
        home_dir = tmp_path / "home"
        monkeypatch.setenv("HOME", str(home_dir))

        await transport._copy_skill_files(str(tmp_path))

        dest_dir = home_dir / ".autohand" / "skills" / "custom-skill"
        dest_file = dest_dir / "SKILL.md"
        assert dest_dir.exists()
        assert dest_file.exists()
        assert dest_file.read_text() == "# Custom Skill"

    @pytest.mark.asyncio
    async def test_copy_skill_files_can_be_disabled(self, tmp_path: Path, monkeypatch) -> None:
        skill_file = tmp_path / "custom-skill.md"
        skill_file.write_text("# Custom Skill")

        transport = Transport(
            TransportOptions(skills=["./custom-skill.md"], copy_skill_files=False)
        )
        home_dir = tmp_path / "home"
        monkeypatch.setenv("HOME", str(home_dir))

        await transport._copy_skill_files(str(tmp_path))

        skills_dir = home_dir / ".autohand" / "skills"
        assert not skills_dir.exists()


class TestTransportDetectCLIBinary:
    """Tests for CLI binary detection."""

    def test_detects_known_platform(self) -> None:
        transport = Transport()
        result = transport._detect_cli_binary()
        assert isinstance(result, str)
        assert result.startswith("autohand-")

    def test_detects_package_path(self, tmp_path: Path) -> None:
        transport = Transport()
        # Create mock package structure
        cli_dir = tmp_path / "cli"
        cli_dir.mkdir()
        binary_name = "autohand-macos-arm64" if sys.platform == "darwin" else "autohand-linux-x64"
        binary = cli_dir / binary_name
        binary.write_text("echo '{}'", encoding="utf-8")
        binary.chmod(0o755)

        # This test validates the detection logic works
        result = transport._detect_cli_binary()
        assert result  # Returns something


class TestTransportRequest:
    """Tests for request method."""

    @pytest.mark.asyncio
    async def test_request_not_started(self) -> None:
        transport = Transport()
        with pytest.raises(RuntimeError, match="Transport not started"):
            await transport.request("prompt", {"message": "test"})

    @pytest.mark.asyncio
    async def test_request_round_trip(self, mock_cli_binary: Path) -> None:
        transport = Transport(TransportOptions(cli_path=str(mock_cli_binary), timeout=1000))
        await transport.start()
        try:
            result = await transport.request("autohand.getState", {})
        finally:
            await transport.stop()

        assert result == {"success": True}

    @pytest.mark.asyncio
    async def test_request_error_response(self, tmp_path: Path) -> None:
        cli_path = tmp_path / "error-cli.py"
        cli_path.write_text(
            "#!/usr/bin/env python3\n"
            "import json, sys\n"
            "for line in sys.stdin:\n"
            "    req = json.loads(line)\n"
            "    print(json.dumps({\n"
            "        'jsonrpc': '2.0',\n"
            "        'id': req.get('id'),\n"
            "        'error': {'code': -32601, 'message': 'Nope', 'data': {'method': req.get('method')}}\n"
            "    }), flush=True)\n",
            encoding="utf-8",
        )
        cli_path.chmod(0o755)

        transport = Transport(TransportOptions(cli_path=str(cli_path), timeout=1000))
        await transport.start()
        try:
            with pytest.raises(RPCError) as exc_info:
                await transport.request("autohand.missing", {})
        finally:
            await transport.stop()

        assert exc_info.value.code == -32601
        assert exc_info.value.data == {"method": "autohand.missing"}

    @pytest.mark.asyncio
    async def test_request_timeout(self, tmp_path: Path) -> None:
        cli_path = tmp_path / "silent-cli.py"
        cli_path.write_text(
            "#!/usr/bin/env python3\n"
            "import time, sys\n"
            "for _line in sys.stdin:\n"
            "    time.sleep(1)\n",
            encoding="utf-8",
        )
        cli_path.chmod(0o755)

        transport = Transport(TransportOptions(cli_path=str(cli_path), timeout=50))
        await transport.start()
        try:
            with pytest.raises(RequestTimeoutError):
                await transport.request("autohand.getState", {})
        finally:
            await transport.stop()

    @pytest.mark.asyncio
    async def test_notifications_and_batch_responses(self) -> None:
        transport = Transport()
        events: list[dict] = []
        unsubscribe = transport.on_notification("autohand.messageUpdate", events.append)
        transport.on_notification("*", events.append)

        response_future = asyncio.get_running_loop().create_future()
        transport._callbacks[1] = response_future
        transport._handle_stdout_line(
            json.dumps(
                [
                    {"jsonrpc": "2.0", "result": {"ok": True}, "id": 1},
                    {
                        "jsonrpc": "2.0",
                        "method": "autohand.messageUpdate",
                        "params": {"delta": "hello"},
                    },
                ]
            ).encode()
        )
        unsubscribe()
        transport._handle_stdout_line(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "method": "autohand.messageUpdate",
                    "params": {"delta": "ignored-by-specific"},
                }
            ).encode()
        )
        transport._handle_stdout_line(b"not json\n")

        assert response_future.result() == {"jsonrpc": "2.0", "result": {"ok": True}, "id": 1}
        assert events[0]["delta"] == "hello"
        assert events[0]["_method"] == "autohand.messageUpdate"
        assert events[1]["delta"] == "hello"
        assert events[2]["delta"] == "ignored-by-specific"


class TestTransportStartArguments:
    """Tests for CLI argument construction."""

    @pytest.mark.asyncio
    async def test_start_builds_cli_args_and_env(self, tmp_path: Path) -> None:
        args_file = tmp_path / "args.json"
        cli_path = tmp_path / "args-cli.py"
        cli_path.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "from pathlib import Path\n"
            "Path(os.environ['ARGS_FILE']).write_text(json.dumps({\n"
            "    'argv': sys.argv[1:],\n"
            "    'cwd': os.getcwd(),\n"
            "    'stream': os.environ.get('AUTOHAND_STREAM_TOOL_OUTPUT'),\n"
            "    'debug': os.environ.get('AUTOHAND_DEBUG'),\n"
            "}))\n"
            "for _line in sys.stdin:\n"
            "    pass\n",
            encoding="utf-8",
        )
        cli_path.chmod(0o755)

        transport = Transport(
            TransportOptions(
                cwd=str(tmp_path),
                cli_path=str(cli_path),
                unrestricted=True,
                auto_mode=True,
                auto_skill=True,
                model="fantail2",
                temperature=0.4,
                max_iterations=5,
                max_runtime=10,
                max_cost=1.25,
                sys_prompt="system",
                append_sys_prompt="append",
                yolo="git status",
                yolo_timeout=30,
                add_dir=["../shared"],
                extra_args=["--custom"],
                skills=["typescript"],
                skill_sources=["autohand-user"],
                install_missing_skills=True,
                permission_mode="default",
                permission_allow_list=["read"],
                permission_deny_list=["delete"],
                persist_session=True,
                session_id="session-1",
                resume=True,
                continue_session=True,
                session_path=".autohand/session.json",
                auto_save_interval=60,
                context_compact=True,
                max_tokens=1000,
                compression_threshold=0.7,
                summarization_threshold=0.8,
                env_vars={"ARGS_FILE": str(args_file), "AUTOHAND_DEBUG": "1"},
            )
        )
        await transport.start()
        try:
            for _ in range(100):
                if args_file.exists():
                    break
                await asyncio.sleep(0.01)
        finally:
            await transport.stop()

        data = json.loads(args_file.read_text())
        argv = data["argv"]
        assert data["cwd"] == str(tmp_path)
        assert data["stream"] == "1"
        assert data["debug"] == "1"
        assert argv[:2] == ["--mode", "rpc"]
        assert "--unrestricted" in argv
        assert "--auto-mode" in argv
        assert "--auto-skill" in argv
        assert argv[argv.index("--model") : argv.index("--model") + 2] == ["--model", "fantail2"]
        assert argv[argv.index("--skills") : argv.index("--skills") + 2] == ["--skills", "typescript"]
        assert "--custom" in argv


class TestTransportReadStderr:
    """Tests for stderr reading."""

    @pytest.mark.asyncio
    async def test_read_stderr_no_process(self) -> None:
        transport = Transport()
        # Should not raise
        await transport._read_stderr()
