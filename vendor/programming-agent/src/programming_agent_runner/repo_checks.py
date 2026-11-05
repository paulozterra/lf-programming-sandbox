from __future__ import annotations

from pathlib import Path
from typing import Any

from .command_discovery import DiscoveredCommand
from .execution import execute_command
from .hashutil import sha256_evidence_envelope
from .models import Evidence, GateResult, Status

REQUIRED_CATEGORIES = {"build", "lint", "typecheck", "test", "negative_test"}


def _evidence(code: str, head_sha: str, source_ref: str, status: Status, payload: dict[str, Any]) -> Evidence:
    source_system = "LOCAL_PROCESS"
    producer = "RUNNER_REPO_COMMANDS"
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


def _command_outcome(item: dict[str, Any]) -> Status:
    if item.get("returncode") == 0:
        return "PASS"
    text = f"{item.get('stdout', '')}\n{item.get('stderr', '')}"
    if item.get("returncode") == 75 or "BLOCKED_TOOL_UNAVAILABLE" in text:
        return "BLOCKED"
    return "FAIL"


def _payload_for(records: list[dict[str, Any]], outcomes: dict[str, Status], categories: tuple[str, ...]) -> dict[str, Any]:
    selected = [item for item in records if item.get("category") in categories]
    selected_outcomes = {category: outcomes.get(category, "BLOCKED") for category in categories}
    return {"executions": selected, "outcomes": selected_outcomes}


def evaluate_repo_commands(
    root: Path,
    head_sha: str,
    commands: list[DiscoveredCommand],
    *,
    execute_commands: bool,
    missing: list[str],
) -> tuple[list[GateResult], list[Evidence], list[dict[str, Any]]]:
    gates: list[GateResult] = []
    evidence: list[Evidence] = []
    records: list[dict[str, Any]] = []

    if not execute_commands:
        return gates, evidence, records

    if missing:
        gates.extend(
            GateResult(code, "BLOCKED", "Command discovery incomplete")
            for code in ("G_BUILD_TYPECHECK", "G_LINT_FORMAT", "G_TEST_POSITIVE", "G_TEST_NEGATIVE")
        )
        return gates, evidence, records

    by_category = {command.category: command for command in commands}
    for category in sorted(REQUIRED_CATEGORIES):
        try:
            records.append(execute_command(root, by_category[category]).to_dict())
        except Exception as exc:  # fail closed at runner boundary
            records.append({"category": category, "error": str(exc), "returncode": None})

    outcomes: dict[str, Status] = {item["category"]: _command_outcome(item) for item in records}

    build_outcome = outcomes.get("build")
    typecheck_outcome = outcomes.get("typecheck")
    build_status: Status
    if build_outcome == "PASS" and typecheck_outcome == "PASS":
        build_status = "PASS"
    elif "FAIL" in {build_outcome, typecheck_outcome}:
        build_status = "FAIL"
    else:
        build_status = "BLOCKED"

    gate_specs: tuple[tuple[str, str, Status, str, tuple[str, ...]], ...] = (
        ("G_BUILD_TYPECHECK", "E_REPO_BUILD_TYPECHECK", build_status, "Canonical build and typecheck commands executed", ("build", "typecheck")),
        ("G_LINT_FORMAT", "E_REPO_LINT_FORMAT", outcomes.get("lint", "BLOCKED"), "Canonical lint command executed", ("lint",)),
        ("G_TEST_POSITIVE", "E_REPO_TEST_POSITIVE", outcomes.get("test", "BLOCKED"), "Canonical positive test command executed", ("test",)),
        ("G_TEST_NEGATIVE", "E_REPO_TEST_NEGATIVE", outcomes.get("negative_test", "BLOCKED"), "Canonical negative-test command executed", ("negative_test",)),
    )

    for gate_code, evidence_code, status, reason, categories in gate_specs:
        payload = _payload_for(records, outcomes, categories)
        gate_evidence = _evidence(evidence_code, head_sha, str(root), status, payload)
        evidence.append(gate_evidence)
        gates.append(GateResult(gate_code, status, reason, (evidence_code,)))

    return gates, evidence, records
