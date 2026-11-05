from __future__ import annotations

from typing import Any

from .context_builder import build_context_pack
from .hashutil import sha256_evidence_envelope, sha256_json, source_snapshot_sha256
from .models import ContextPack, Evidence, GateResult, RunnerInput, Status
from .validation import validate_head_sha, validate_repo_full_name, validate_repo_path, validate_sha256


def _evidence(
    code: str,
    status: Status,
    source_system: str,
    source_ref: str,
    head_sha: str,
    producer: str,
    payload: dict[str, Any],
) -> Evidence:
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


def validate_input(input_: RunnerInput) -> GateResult | None:
    try:
        validate_repo_path(input_.repo_path)
        validate_repo_full_name(input_.repo_full_name)
        validate_head_sha(input_.head_sha)
        validate_sha256(input_.source_snapshot_sha256)
        actual_snapshot = source_snapshot_sha256(input_.repo_path)
    except ValueError as exc:
        return GateResult("G_RUNNER_INPUT_PINNED", "BLOCKED", str(exc))
    if actual_snapshot != input_.source_snapshot_sha256:
        return GateResult(
            "G_RUNNER_INPUT_PINNED",
            "BLOCKED",
            "SOURCE_SNAPSHOT_MISMATCH",
            metadata={"expected": input_.source_snapshot_sha256, "actual": actual_snapshot},
        )
    return None


def input_evidence(input_: RunnerInput) -> Evidence:
    payload: dict[str, Any] = {
        "repo_path": str(input_.repo_path),
        "repo_full_name": input_.repo_full_name,
        "ref": input_.ref,
        "head_sha": input_.head_sha,
        "source_snapshot_sha256": input_.source_snapshot_sha256,
        "scope": list(input_.scope),
        "version_code": input_.version_code,
        "profile_code": input_.profile_code,
        "worker_task_spec_present": input_.worker_task_spec is not None,
    }
    if input_.worker_task_spec is not None:
        worker_payload = input_.worker_task_spec.to_dict() if hasattr(input_.worker_task_spec, "to_dict") else input_.worker_task_spec
        payload["worker_task_spec_sha256"] = sha256_json(worker_payload)
    return _evidence(
        "E_RUNNER_INPUT",
        "PASS",
        "RUNNER_INPUT",
        input_.repo_full_name,
        input_.head_sha,
        "RUNNER_PREFLIGHT",
        payload,
    )


def evaluate_context(input_: RunnerInput, ekb_snapshot: dict[str, Any] | None) -> tuple[ContextPack, GateResult, Evidence]:
    context = build_context_pack(input_.repo_path, ekb_snapshot)
    evidence = _evidence(
        "E_CONTEXT_PACK",
        "PASS",
        "LOCAL_REPO",
        str(input_.repo_path),
        input_.head_sha,
        "RUNNER_CONTEXT",
        context.to_dict(),
    )
    status: Status = "BLOCKED" if context.ekb_snapshot.get("status") == "MISSING_CONTEXT" else "PASS"
    gate = GateResult(
        "G_RUNNER_CONTEXT_COMPLETE",
        status,
        "EKB snapshot is missing" if status == "BLOCKED" else "Context Pack complete",
        (evidence.code,),
    )
    return context, gate, evidence
