from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, cast

from .analysis_checks import evaluate_ast, evaluate_command_discovery, evaluate_dependency
from .ekb_checks import evaluate_ekb_regressions
from .evidence_validation import validate_evidence_envelope
from .execution_fingerprint import evaluate_execution_fingerprint
from .github_checks import evaluate_github
from .github_reader import GitHubReadClient
from .hashutil import sha256_evidence_envelope, sha256_json
from .learning_metrics import build_learning_efficiency_metrics, validate_learning_efficiency_metrics
from .models import Evidence, GateResult, RunnerInput, Status
from .preflight_checks import evaluate_context, input_evidence, validate_input
from .repo_checks import evaluate_repo_commands
from .worker_task_spec import evaluate_worker_task_spec


def _status(value: Any) -> Status:
    if value not in {"PASS", "FAIL", "BLOCKED", "NOT_APPLICABLE"}:
        raise ValueError(f"invalid status: {value!r}")
    return cast(Status, value)


def _envelope_evidence(input_: RunnerInput, payload: dict[str, Any], status: Status) -> Evidence:
    code = "E_EVIDENCE_ENVELOPE"
    source_system = "RUNNER"
    source_ref = input_.repo_full_name
    producer = "RUNNER_RUNTIME_WRITER"
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
            head_sha=input_.head_sha,
            producer=producer,
            metadata=payload,
        ),
        head_sha=input_.head_sha,
        producer=producer,
        metadata=payload,
    )


def _github_test_execution(github_evidence: list[Evidence]) -> dict[str, Any] | None:
    for item in github_evidence:
        if item.code != "E_GITHUB_CI":
            continue
        receipt = item.metadata.get("test_execution_receipt")
        if not isinstance(receipt, dict):
            return None
        return receipt
    return None


def run_reference(
    input_: RunnerInput,
    *,
    ekb_snapshot: dict[str, Any] | None = None,
    github: GitHubReadClient | None = None,
    execute_commands: bool = False,
) -> dict[str, Any]:
    input_failure = validate_input(input_)
    if input_failure:
        return {
            "runner_version": input_.version_code,
            "artifact_status": "NON_CANONICAL_LOCAL_ARTIFACT",
            "status": "BLOCKED",
            "gates": [input_failure.to_dict()],
            "evidence": [],
        }

    gates: list[GateResult] = []
    evidence: list[Evidence] = []

    preflight_evidence = input_evidence(input_)
    evidence.append(preflight_evidence)
    gates.append(GateResult("G_RUNNER_INPUT_PINNED", "PASS", "Input contract validated", (preflight_evidence.code,)))

    _, worker_spec_gate, worker_spec_evidence = evaluate_worker_task_spec(input_, required=execute_commands)
    gates.append(worker_spec_gate)
    evidence.append(worker_spec_evidence)
    command_execution_authorized = execute_commands and worker_spec_gate.status == "PASS"

    context, context_gate, context_evidence = evaluate_context(input_, ekb_snapshot)
    gates.append(context_gate)
    evidence.append(context_evidence)

    fingerprint_gate, fingerprint_evidence = evaluate_execution_fingerprint(input_, context_evidence.sha256)
    gates.append(fingerprint_gate)
    evidence.append(fingerprint_evidence)

    dependency_gate, dependency_evidence = evaluate_dependency(input_, context)
    gates.append(dependency_gate)
    evidence.append(dependency_evidence)

    commands, missing, command_gate, command_evidence = evaluate_command_discovery(input_)
    gates.append(command_gate)
    evidence.append(command_evidence)

    repo_gates, repo_evidence, execution_records = evaluate_repo_commands(
        input_.repo_path,
        input_.head_sha,
        commands,
        execute_commands=command_execution_authorized,
        missing=missing,
    )
    gates.extend(repo_gates)
    evidence.extend(repo_evidence)

    ast_gate, ast_evidence = evaluate_ast(input_)
    gates.append(ast_gate)
    evidence.append(ast_evidence)

    github_gates, github_evidence = evaluate_github(input_, github)
    gates.extend(github_gates)
    evidence.extend(github_evidence)

    test_execution_receipt = _github_test_execution(github_evidence)
    ekb_gate, ekb_evidence = evaluate_ekb_regressions(
        input_,
        context,
        test_execution_receipt=test_execution_receipt,
    )
    gates.append(ekb_gate)
    evidence.append(ekb_evidence)

    envelope_payload = validate_evidence_envelope(input_.head_sha, evidence, gates)
    envelope_status = _status(envelope_payload["status"])
    envelope_evidence = _envelope_evidence(input_, envelope_payload, envelope_status)
    evidence.append(envelope_evidence)
    gates.append(
        GateResult(
            "G_RUNNER_EVIDENCE_WRITE",
            envelope_status,
            "Evidence envelope internally coherent" if envelope_status == "PASS" else "Evidence envelope rejected",
            (envelope_evidence.code,),
            envelope_payload,
        )
    )

    learning_efficiency_metrics = build_learning_efficiency_metrics(
        context_bytes_or_tokens=len(
            json.dumps(context, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        )
    )
    validate_learning_efficiency_metrics(learning_efficiency_metrics)

    blocking = [gate for gate in gates if gate.status in {"FAIL", "BLOCKED"}]
    status: Status = "PASS" if not blocking else "BLOCKED" if all(gate.status == "BLOCKED" for gate in blocking) else "FAIL"
    serialized_input = asdict(input_)
    serialized_input["repo_path"] = str(input_.repo_path)
    if input_.worker_task_spec is not None:
        worker_payload = input_.worker_task_spec.to_dict() if hasattr(input_.worker_task_spec, "to_dict") else input_.worker_task_spec
        serialized_input["worker_task_spec_sha256"] = sha256_json(worker_payload)
        serialized_input["worker_task_spec"] = worker_payload
    output: dict[str, Any] = {
        "runner_version": input_.version_code,
        "artifact_status": "NON_CANONICAL_LOCAL_ARTIFACT",
        "status": status,
        "input": serialized_input,
        "context_pack_sha256": context_evidence.sha256,
        "ekb_regression_coverage_sha256": ekb_evidence.sha256,
        "execution_fingerprint_sha256": fingerprint_evidence.metadata["execution_fingerprint_sha256"],
        "learning_efficiency_metrics": learning_efficiency_metrics,
        "gates": [gate.to_dict() for gate in gates],
        "evidence": [item.to_dict() for item in evidence],
        "command_executions": execution_records,
    }
    output["run_sha256"] = sha256_json(output)
    return output
