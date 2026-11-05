from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .worker_spec import AcceptanceCommand


@dataclass(frozen=True)
class AcceptanceResult:
    name: str
    argv: tuple[str, ...]
    status: str
    reason: str
    returncode: int | None
    stdout: str
    stderr: str
    duration_ms: int

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["argv"] = list(self.argv)
        return value


def _command_environment(runtime_root: Path) -> dict[str, str]:
    home = runtime_root / "home"
    temporary = runtime_root / "tmp"
    home.mkdir(parents=True, exist_ok=True)
    temporary.mkdir(parents=True, exist_ok=True)
    return {
        "CI": "true",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "NO_COLOR": "1",
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "PYTHON": sys.executable,
        "PYTHONDONTWRITEBYTECODE": "1",
        "TEMP": str(temporary),
        "TMP": str(temporary),
        "TMPDIR": str(temporary),
    }


def _terminate_group(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except ProcessLookupError:
        return


def _bounded_text(handle: Any, maximum: int) -> str:
    handle.flush()
    handle.seek(0)
    data = handle.read(maximum + 1)
    if len(data) > maximum:
        data = data[:maximum]
    return data.decode("utf-8", errors="replace")


def run_acceptance_command(workspace: Path, command: AcceptanceCommand) -> AcceptanceResult:
    started = time.monotonic()
    reason = "EXIT_NONZERO"
    with (
        tempfile.TemporaryDirectory(prefix="programming-agent-command-") as runtime_directory,
        tempfile.TemporaryFile() as stdout_file,
        tempfile.TemporaryFile() as stderr_file,
    ):
        try:
            process = subprocess.Popen(
                command.argv,
                cwd=workspace,
                env=_command_environment(Path(runtime_directory)),
                stdin=subprocess.DEVNULL,
                stdout=stdout_file,
                stderr=stderr_file,
                start_new_session=True,
            )
        except OSError as exc:
            duration = int((time.monotonic() - started) * 1000)
            return AcceptanceResult(
                command.name,
                command.argv,
                "BLOCKED",
                f"COMMAND_START_FAILED: {type(exc).__name__}",
                None,
                "",
                "",
                duration,
            )
        deadline = started + command.timeout_seconds
        while process.poll() is None:
            output_size = os.fstat(stdout_file.fileno()).st_size + os.fstat(stderr_file.fileno()).st_size
            if output_size > command.max_output_bytes:
                reason = "OUTPUT_LIMIT_EXCEEDED"
                _terminate_group(process)
                break
            if time.monotonic() >= deadline:
                reason = "TIMEOUT"
                _terminate_group(process)
                break
            time.sleep(0.02)
        try:
            returncode = process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            _terminate_group(process)
            returncode = process.wait()
        output_size = os.fstat(stdout_file.fileno()).st_size + os.fstat(stderr_file.fileno()).st_size
        if output_size > command.max_output_bytes:
            reason = "OUTPUT_LIMIT_EXCEEDED"
        elif reason not in ("TIMEOUT", "OUTPUT_LIMIT_EXCEEDED"):
            reason = "COMMAND_SUCCEEDED" if returncode == 0 else "EXIT_NONZERO"
        status = "PASS" if reason == "COMMAND_SUCCEEDED" else "FAIL"
        duration = int((time.monotonic() - started) * 1000)
        return AcceptanceResult(
            command.name,
            command.argv,
            status,
            reason,
            returncode,
            _bounded_text(stdout_file, command.max_output_bytes),
            _bounded_text(stderr_file, command.max_output_bytes),
            duration,
        )


def run_acceptance_suite(workspace: Path, commands: tuple[AcceptanceCommand, ...]) -> tuple[AcceptanceResult, ...]:
    results: list[AcceptanceResult] = []
    for command in commands:
        result = run_acceptance_command(workspace, command)
        results.append(result)
        if result.status != "PASS":
            break
    return tuple(results)
