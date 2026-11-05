from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import PurePosixPath
from typing import Any

from .hashutil import sha256_json
from .worker_secrets import secret_text_reason

TASK_SCHEMA_VERSION = 1
_TASK_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_HEX40 = re.compile(r"[0-9a-f]{40}\Z")
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_COMMAND_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
_TASK_FIELDS = {
    "schema_version",
    "task_id",
    "objective",
    "base_head_sha",
    "source_snapshot_sha256",
    "context_path_patterns",
    "write_path_patterns",
    "protected_path_patterns",
    "acceptance_commands",
    "max_attempts",
    "max_patch_bytes",
    "max_changed_files",
    "max_context_bytes",
    "allow_deletions",
}
_COMMAND_FIELDS = {"name", "argv", "timeout_seconds", "max_output_bytes"}


class TaskSpecError(ValueError):
    """Raised when an owner-supplied worker task is not exact or safe enough to run."""


@dataclass(frozen=True)
class AcceptanceCommand:
    name: str
    argv: tuple[str, ...]
    timeout_seconds: int
    max_output_bytes: int

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["argv"] = list(self.argv)
        return value


@dataclass(frozen=True)
class WorkerTaskSpec:
    schema_version: int
    task_id: str
    objective: str
    base_head_sha: str
    source_snapshot_sha256: str
    context_path_patterns: tuple[str, ...]
    write_path_patterns: tuple[str, ...]
    protected_path_patterns: tuple[str, ...]
    acceptance_commands: tuple[AcceptanceCommand, ...]
    max_attempts: int
    max_patch_bytes: int
    max_changed_files: int
    max_context_bytes: int
    allow_deletions: bool

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["context_path_patterns"] = list(self.context_path_patterns)
        value["write_path_patterns"] = list(self.write_path_patterns)
        value["protected_path_patterns"] = list(self.protected_path_patterns)
        value["acceptance_commands"] = [command.to_dict() for command in self.acceptance_commands]
        return value

    @property
    def sha256(self) -> str:
        return sha256_json(self.to_dict())


def _exact_int(value: Any, field: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise TaskSpecError(f"{field} must be an integer in [{minimum}, {maximum}]")
    return value


def canonical_relative_path(value: Any, field: str = "path") -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 1024:
        raise TaskSpecError(f"{field} must be a non-empty relative UTF-8 path")
    if "\0" in value or "\\" in value or value.startswith("/") or any(ord(character) < 32 for character in value):
        raise TaskSpecError(f"{field} is not a canonical POSIX relative path: {value!r}")
    path = PurePosixPath(value)
    parts = path.parts
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise TaskSpecError(f"{field} is not a canonical POSIX relative path: {value!r}")
    if ".git" in parts:
        raise TaskSpecError(f"{field} cannot address Git control data")
    canonical = path.as_posix()
    if canonical != value:
        raise TaskSpecError(f"{field} must be canonical: {value!r}")
    return canonical


def _validate_pattern(value: Any, field: str) -> str:
    pattern = canonical_relative_path(value, field)
    for segment in pattern.split("/"):
        if "**" in segment and segment != "**":
            raise TaskSpecError(f"{field} may use ** only as a complete path segment")
        if any(character in segment for character in "[]{}"):
            raise TaskSpecError(f"{field} supports only literal segments, *, ?, and **")
    return pattern


def _segment_matches(name: str, pattern: str) -> bool:
    expression = ""
    for character in pattern:
        if character == "*":
            expression += "[^/]*"
        elif character == "?":
            expression += "[^/]"
        else:
            expression += re.escape(character)
    return re.fullmatch(expression, name) is not None


def path_matches_pattern(path: str, pattern: str) -> bool:
    path_parts = tuple(PurePosixPath(path).parts)
    pattern_parts = tuple(PurePosixPath(pattern).parts)

    @lru_cache(maxsize=None)
    def match(path_index: int, pattern_index: int) -> bool:
        if pattern_index == len(pattern_parts):
            return path_index == len(path_parts)
        current = pattern_parts[pattern_index]
        if current == "**":
            return match(path_index, pattern_index + 1) or (
                path_index < len(path_parts) and match(path_index + 1, pattern_index)
            )
        return (
            path_index < len(path_parts)
            and _segment_matches(path_parts[path_index], current)
            and match(path_index + 1, pattern_index + 1)
        )

    return match(0, 0)


def path_matches_any(path: str, patterns: tuple[str, ...]) -> bool:
    return any(path_matches_pattern(path, pattern) for pattern in patterns)


def _string_list(value: Any, field: str, maximum: int) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or len(value) > maximum:
        raise TaskSpecError(f"{field} must be a non-empty array with at most {maximum} entries")
    result = tuple(_validate_pattern(item, f"{field}[]") for item in value)
    if len(set(result)) != len(result):
        raise TaskSpecError(f"{field} contains duplicates")
    return result


def _acceptance_commands(value: Any) -> tuple[AcceptanceCommand, ...]:
    if not isinstance(value, list) or not value or len(value) > 32:
        raise TaskSpecError("acceptance_commands must contain between 1 and 32 commands")
    commands: list[AcceptanceCommand] = []
    names: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, dict) or set(item) != _COMMAND_FIELDS:
            raise TaskSpecError(f"acceptance_commands[{index}] fields must be exactly {sorted(_COMMAND_FIELDS)}")
        name = item["name"]
        if not isinstance(name, str) or _COMMAND_NAME.fullmatch(name) is None or name in names:
            raise TaskSpecError(f"acceptance_commands[{index}].name is invalid or duplicated")
        argv_value = item["argv"]
        if not isinstance(argv_value, list) or not 1 <= len(argv_value) <= 64:
            raise TaskSpecError(f"acceptance_commands[{index}].argv must contain between 1 and 64 arguments")
        argv: list[str] = []
        for argument in argv_value:
            if (
                not isinstance(argument, str)
                or not argument
                or "\0" in argument
                or len(argument.encode("utf-8")) > 4096
            ):
                raise TaskSpecError(f"acceptance_commands[{index}].argv contains an invalid argument")
            if secret_text_reason(argument):
                raise TaskSpecError(f"acceptance_commands[{index}].argv contains a probable secret")
            argv.append(argument)
        commands.append(
            AcceptanceCommand(
                name=name,
                argv=tuple(argv),
                timeout_seconds=_exact_int(item["timeout_seconds"], "timeout_seconds", 1, 900),
                max_output_bytes=_exact_int(item["max_output_bytes"], "max_output_bytes", 1024, 2_000_000),
            )
        )
        names.add(name)
    return tuple(commands)


def parse_worker_task(value: Any) -> WorkerTaskSpec:
    if not isinstance(value, dict) or set(value) != _TASK_FIELDS:
        raise TaskSpecError(f"task fields must be exactly {sorted(_TASK_FIELDS)}")
    if value["schema_version"] != TASK_SCHEMA_VERSION or type(value["schema_version"]) is not int:
        raise TaskSpecError(f"schema_version must be exactly {TASK_SCHEMA_VERSION}")
    task_id = value["task_id"]
    if not isinstance(task_id, str) or _TASK_ID.fullmatch(task_id) is None:
        raise TaskSpecError("task_id is invalid")
    objective = value["objective"]
    if not isinstance(objective, str) or not objective.strip() or len(objective.encode("utf-8")) > 20_000:
        raise TaskSpecError("objective must be non-empty and at most 20000 UTF-8 bytes")
    if secret_text_reason(objective):
        raise TaskSpecError("objective contains a probable secret")
    if not isinstance(value["base_head_sha"], str) or _HEX40.fullmatch(value["base_head_sha"]) is None:
        raise TaskSpecError("base_head_sha must be a lowercase 40-hex Git SHA")
    snapshot = value["source_snapshot_sha256"]
    if not isinstance(snapshot, str) or _HEX64.fullmatch(snapshot) is None:
        raise TaskSpecError("source_snapshot_sha256 must be a lowercase SHA-256")
    if type(value["allow_deletions"]) is not bool:
        raise TaskSpecError("allow_deletions must be boolean")
    return WorkerTaskSpec(
        schema_version=TASK_SCHEMA_VERSION,
        task_id=task_id,
        objective=objective,
        base_head_sha=value["base_head_sha"],
        source_snapshot_sha256=snapshot,
        context_path_patterns=_string_list(value["context_path_patterns"], "context_path_patterns", 256),
        write_path_patterns=_string_list(value["write_path_patterns"], "write_path_patterns", 128),
        protected_path_patterns=_string_list(value["protected_path_patterns"], "protected_path_patterns", 128),
        acceptance_commands=_acceptance_commands(value["acceptance_commands"]),
        max_attempts=_exact_int(value["max_attempts"], "max_attempts", 1, 5),
        max_patch_bytes=_exact_int(value["max_patch_bytes"], "max_patch_bytes", 1, 1_000_000),
        max_changed_files=_exact_int(value["max_changed_files"], "max_changed_files", 1, 100),
        max_context_bytes=_exact_int(value["max_context_bytes"], "max_context_bytes", 1024, 2_000_000),
        allow_deletions=value["allow_deletions"],
    )
