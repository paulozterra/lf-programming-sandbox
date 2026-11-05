from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .command_discovery import DiscoveredCommand

SAFE_ENV_KEYS = {
    "HOME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "PATH",
    "SYSTEMROOT",
    "TMP",
    "TEMP",
    "TMPDIR",
    "USERPROFILE",
}


@dataclass(frozen=True)
class CommandExecution:
    category: str
    command: tuple[str, ...]
    source: str
    returncode: int
    stdout: str
    stderr: str

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["command"] = list(self.command)
        return value


def _materialize(command: DiscoveredCommand) -> tuple[str, ...]:
    if command.command and command.command[0] == "python-project-script":
        # The pyproject entry is explicit, but invocation semantics are not. Fail closed.
        raise RuntimeError("pyproject project.scripts entry discovered but invocation is unresolved; execution BLOCKED")
    return command.command


def _safe_environment() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key in SAFE_ENV_KEYS}
    env["PYTHON"] = sys.executable
    return env


def execute_command(root: Path, command: DiscoveredCommand, timeout: int = 300) -> CommandExecution:
    argv = _materialize(command)
    proc = subprocess.run(
        argv,
        cwd=root,
        env=_safe_environment(),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return CommandExecution(command.category, argv, command.source, proc.returncode, proc.stdout, proc.stderr)
