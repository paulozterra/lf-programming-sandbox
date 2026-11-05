from __future__ import annotations

from typing import Any, cast

from .ast_analysis import analyze_python
from .command_discovery import DiscoveredCommand, discover_commands
from .dependency_verify import verify_dependencies
from .hashutil import sha256_evidence_envelope
from .models import ContextPack, Evidence, GateResult, RunnerInput, Status
from .repo_checks import REQUIRED_CATEGORIES


def _status(value: Any) -> Status:
    if value not in {"PASS", "FAIL", "BLOCKED", "NOT_APPLICABLE"}:
        raise ValueError(f"invalid status: {value!r}")
    return cast(Status, value)


def _evidence(
    code: str,
    status: Status,
    source_ref: str,
    head_sha: str,
    producer: str,
    payload: dict[str, Any],
) -> Evidence:
    source_system = "LOCAL_REPO"
    return Evidence(
        code=code,
        status=status,
        source_system=source_system,
        source_ref=source_ref,
        sha256=sha256_evidence_envelope(
            code=code,
            status=status,
            source_system=source_system,
            source_ref=source_ref,
            head_sha=head_sha,
            producer=producer,
            metadata=payload,
        ),
        head_sha=head_sha,
        producer=producer,
        metadata=payload,
    )


def evaluate_dependency(input_: RunnerInput, context: ContextPack) -> tuple[GateResult, Evidence]:
    payload = verify_dependencies(input_.repo_path, context.dependency_inventory)
    status = _status(payload["status"])
    evidence = _evidence(
        "E_DEPENDENCY_VERIFY",
        status,
        str(input_.repo_path),
        input_.head_sha,
        "RUNNER_PYTHON_ANALYSIS",
        payload,
    )
    gate = GateResult(
        "G_RUNNER_DEPENDENCY_VERIFY",
        status,
        "Dependency resolution verified" if status == "PASS" else "Dependency resolution unresolved",
        (evidence.code,),
        payload,
    )
    return gate, evidence


def evaluate_command_discovery(input_: RunnerInput) -> tuple[list[DiscoveredCommand], list[str], GateResult, Evidence]:
    commands = discover_commands(input_.repo_path)
    payload = {"commands": [command.to_dict() for command in commands]}
    evidence = _evidence(
        "E_COMMAND_DISCOVERY",
        "PASS",
        str(input_.repo_path),
        input_.head_sha,
        "RUNNER_REPO_COMMANDS",
        payload,
    )
    missing = sorted(REQUIRED_CATEGORIES - {command.category for command in commands})
    gate = GateResult(
        "G_RUNNER_COMMAND_DISCOVERY",
        "BLOCKED" if missing else "PASS",
        f"Required canonical commands unresolved: {', '.join(missing)}" if missing else "All canonical commands explicitly discovered",
        (evidence.code,),
        {"missing": missing},
    )
    return commands, missing, gate, evidence


def evaluate_ast(input_: RunnerInput) -> tuple[GateResult, Evidence]:
    payload = analyze_python(input_.repo_path)
    status: Status = "BLOCKED" if payload["parse_errors"] else "PASS"
    evidence = _evidence(
        "E_AST_ANALYSIS",
        status,
        str(input_.repo_path),
        input_.head_sha,
        "RUNNER_PYTHON_ANALYSIS",
        payload,
    )
    gate = GateResult(
        "G_RUNNER_AST_ANALYSIS",
        status,
        "Python parse error" if status == "BLOCKED" else "AST analysis completed without invented thresholds",
        (evidence.code,),
    )
    return gate, evidence
