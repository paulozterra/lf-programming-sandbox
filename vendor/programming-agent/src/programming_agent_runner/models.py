from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

Status = Literal["PASS", "FAIL", "BLOCKED", "NOT_APPLICABLE"]
ExecutionMode = Literal["legacy", "deterministic", "probabilistic"]


@dataclass(frozen=True)
class WorkerTaskSpecV2:
    schema_version: int
    task_id: str
    objective: str
    expected_change: str
    human_story: dict[str, Any]
    functional_contract: dict[str, Any]
    scope: dict[str, Any]
    cases: dict[str, Any]
    dependency_resolution: list[dict[str, Any]]
    dependency_task_ids: list[int]
    required_tests: list[dict[str, Any]]
    required_evidence: list[dict[str, Any]]
    blocked_if: list[dict[str, Any]]
    base_head_sha: str
    source_snapshot_sha256: str
    context_path_patterns: list[str]
    write_path_patterns: list[str]
    protected_path_patterns: list[str]
    files_expected: list[str]
    platform_refs: list[str]
    interface_refs: list[str]
    acceptance_commands: list[dict[str, Any]]
    max_attempts: int
    max_patch_bytes: int
    max_changed_files: int
    max_context_bytes: int
    allow_deletions: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RunnerInput:
    repo_path: Path
    repo_full_name: str
    ref: str
    head_sha: str
    source_snapshot_sha256: str
    scope: tuple[str, ...] = ()
    version_code: str = "v0.5-local-reference"
    profile_code: str = "QC_BASE_V02"
    execution_mode: ExecutionMode = "legacy"
    model_provider: str = "none"
    model_identifier: str = "none"
    instruction_sha256: str | None = None
    toolchain_sha256: str | None = None
    expected_execution_fingerprint_sha256: str | None = None
    worker_task_spec: WorkerTaskSpecV2 | dict[str, Any] | None = None


@dataclass(frozen=True)
class Evidence:
    code: str
    status: Status
    source_system: str
    source_ref: str
    sha256: str
    head_sha: str
    producer: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GateResult:
    gate_code: str
    status: Status
    reason: str
    evidence_codes: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ContextPack:
    repository_inventory: dict[str, Any]
    dependency_inventory: dict[str, Any]
    architecture_inventory: dict[str, Any]
    configuration_inventory: dict[str, Any]
    test_inventory: dict[str, Any]
    migration_inventory: dict[str, Any]
    public_api_inventory: dict[str, Any]
    ekb_snapshot: dict[str, Any]
    provenance: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
