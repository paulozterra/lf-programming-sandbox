from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .hashutil import sha256_bytes, sha256_json, strict_json_loads
from .worker_commands import AcceptanceResult, run_acceptance_suite
from .worker_spec import AcceptanceCommand, TaskSpecError, _acceptance_commands

ORACLE_MANIFEST_SCHEMA_VERSION = 1
_ORACLE_FIELDS = {"schema_version", "family", "version", "commands"}


class OracleError(RuntimeError):
    """Raised when a hidden acceptance oracle cannot be proven immutable and isolated."""


@dataclass(frozen=True)
class HiddenOracle:
    path: Path
    family: str
    version: str
    manifest_sha256: str
    commands: tuple[AcceptanceCommand, ...]

    def assert_pinned(self) -> None:
        observed = _read_bytes(self.path)
        digest = sha256_bytes(observed)
        if digest != self.manifest_sha256:
            raise OracleError(
                f"HIDDEN_ORACLE_DRIFT: expected {self.manifest_sha256}, observed {digest}"
            )


@dataclass(frozen=True)
class HiddenOracleResult:
    status: str
    reason: str
    family: str
    version: str
    manifest_sha256: str
    command_count: int
    passed_count: int
    result_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason": self.reason,
            "family": self.family,
            "version": self.version,
            "manifest_sha256": self.manifest_sha256,
            "command_count": self.command_count,
            "passed_count": self.passed_count,
            "result_sha256": self.result_sha256,
        }


def _absolute_no_resolve(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _inside(path: Path, repository: Path) -> bool:
    return path == repository or path.is_relative_to(repository)


def _same_file_inside_repository(repository: Path, oracle_path: Path) -> bool:
    """Return True when any repo path resolves to the same filesystem object as the oracle."""
    try:
        oracle_stat = oracle_path.stat()
    except OSError as exc:
        raise OracleError(f"HIDDEN_ORACLE_LOCATION_UNRESOLVABLE: {type(exc).__name__}") from exc
    try:
        for candidate in repository.rglob("*"):
            try:
                candidate_stat = candidate.stat()
            except OSError as exc:
                raise OracleError(f"HIDDEN_ORACLE_LOCATION_UNRESOLVABLE: {type(exc).__name__}") from exc
            if not stat.S_ISREG(candidate_stat.st_mode):
                continue
            if (candidate_stat.st_dev, candidate_stat.st_ino) == (oracle_stat.st_dev, oracle_stat.st_ino):
                return True
    except OSError as exc:
        raise OracleError(f"HIDDEN_ORACLE_LOCATION_UNRESOLVABLE: {type(exc).__name__}") from exc
    return False


def assert_hidden_oracle_external(repo_path: Path, oracle: HiddenOracle) -> None:
    """Fail closed if the oracle path or underlying file object is repo-local."""
    repository_lexical = _absolute_no_resolve(repo_path)
    oracle_lexical = _absolute_no_resolve(oracle.path)
    try:
        repository_resolved = repo_path.resolve(strict=True)
        oracle_resolved = oracle.path.resolve(strict=True)
    except OSError as exc:
        raise OracleError(f"HIDDEN_ORACLE_LOCATION_UNRESOLVABLE: {type(exc).__name__}") from exc
    if _inside(oracle_lexical, repository_lexical) or _inside(oracle_resolved, repository_resolved):
        raise OracleError("HIDDEN_ORACLE_INSIDE_SOURCE_REPOSITORY")
    if _same_file_inside_repository(repository_resolved, oracle_resolved):
        raise OracleError("HIDDEN_ORACLE_FILE_OBJECT_INSIDE_SOURCE_REPOSITORY")


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise OracleError(f"HIDDEN_ORACLE_UNREADABLE: {type(exc).__name__}") from exc


def _short_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 256:
        raise OracleError(f"{field} must be non-empty UTF-8 text <= 256 bytes")
    return value


def load_hidden_oracle(path: Path, expected_sha256: str) -> HiddenOracle:
    if len(expected_sha256) != 64 or any(character not in "0123456789abcdef" for character in expected_sha256):
        raise OracleError("HIDDEN_ORACLE_EXPECTED_SHA256_INVALID")
    data = _read_bytes(path)
    observed_sha256 = sha256_bytes(data)
    if observed_sha256 != expected_sha256:
        raise OracleError(
            f"HIDDEN_ORACLE_DIGEST_MISMATCH: expected {expected_sha256}, observed {observed_sha256}"
        )
    try:
        value = strict_json_loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        raise OracleError(f"HIDDEN_ORACLE_JSON_INVALID: {type(exc).__name__}") from exc
    if not isinstance(value, dict) or set(value) != _ORACLE_FIELDS:
        raise OracleError(f"hidden oracle fields must be exactly {sorted(_ORACLE_FIELDS)}")
    if type(value["schema_version"]) is not int or value["schema_version"] != ORACLE_MANIFEST_SCHEMA_VERSION:
        raise OracleError(f"hidden oracle schema_version must be {ORACLE_MANIFEST_SCHEMA_VERSION}")
    try:
        commands = _acceptance_commands(value["commands"])
    except TaskSpecError as exc:
        raise OracleError(f"HIDDEN_ORACLE_COMMANDS_INVALID: {exc}") from exc
    oracle = HiddenOracle(
        path=_absolute_no_resolve(path),
        family=_short_text(value["family"], "family"),
        version=_short_text(value["version"], "version"),
        manifest_sha256=observed_sha256,
        commands=commands,
    )
    oracle.assert_pinned()
    return oracle


def hidden_oracle_not_run(oracle: HiddenOracle) -> dict[str, Any]:
    return {
        "status": "NOT_RUN",
        "reason": "VISIBLE_ACCEPTANCE_NOT_PASS",
        "family": oracle.family,
        "version": oracle.version,
        "manifest_sha256": oracle.manifest_sha256,
        "command_count": len(oracle.commands),
        "passed_count": 0,
        "result_sha256": sha256_json({"status": "NOT_RUN", "manifest_sha256": oracle.manifest_sha256}),
    }


def _result_digest(results: tuple[AcceptanceResult, ...]) -> str:
    return sha256_json(
        [
            {
                "status": result.status,
                "reason": result.reason,
                "returncode": result.returncode,
            }
            for result in results
        ]
    )


def run_hidden_oracle(workspace: Path, oracle: HiddenOracle) -> HiddenOracleResult:
    oracle.assert_pinned()
    results = run_acceptance_suite(workspace, oracle.commands)
    oracle.assert_pinned()
    passed = sum(result.status == "PASS" for result in results)
    if len(results) != len(oracle.commands):
        status = "BLOCKED" if any(result.status == "BLOCKED" for result in results) else "FAIL"
        reason = "HIDDEN_ORACLE_INCOMPLETE"
    elif any(result.status == "BLOCKED" for result in results):
        status = "BLOCKED"
        reason = "HIDDEN_ORACLE_COMMAND_BLOCKED"
    elif all(result.status == "PASS" for result in results):
        status = "PASS"
        reason = "HIDDEN_ORACLE_PASSED"
    else:
        status = "FAIL"
        reason = "HIDDEN_ORACLE_FAILED"
    return HiddenOracleResult(
        status=status,
        reason=reason,
        family=oracle.family,
        version=oracle.version,
        manifest_sha256=oracle.manifest_sha256,
        command_count=len(oracle.commands),
        passed_count=passed,
        result_sha256=_result_digest(results),
    )
