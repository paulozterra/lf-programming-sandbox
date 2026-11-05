from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .hashutil import sha256_bytes, sha256_json
from .model_client import ModelClient
from .worker import WorkerResult, run_worker
from .worker_oracle import (
    HiddenOracle,
    OracleError,
    assert_hidden_oracle_external,
    hidden_oracle_not_run,
    run_hidden_oracle,
)
from .worker_spec import WorkerTaskSpec
from .worker_workspace import (
    WorkspaceError,
    copy_candidate_for_commands,
    create_disposable_workspace,
    replay_cumulative_patch,
    verify_source_repository,
)

VERIFIED_WORKER_RECEIPT_SCHEMA_VERSION = 1
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_HIDDEN_FIELDS = {
    "status",
    "reason",
    "family",
    "version",
    "manifest_sha256",
    "command_count",
    "passed_count",
    "result_sha256",
}


@dataclass(frozen=True)
class VerifiedWorkerResult:
    receipt: dict[str, Any]
    patch: str


def oracle_gate_passes(visible_pass: bool, hidden_pass: bool, oracle_stable: bool) -> bool:
    return visible_pass and hidden_pass and oracle_stable


def verified_worker_receipt_sha256(receipt: dict[str, Any]) -> str:
    return sha256_json({key: value for key, value in receipt.items() if key != "receipt_sha256"})


def _sealed(value: dict[str, Any]) -> dict[str, Any]:
    receipt = dict(value)
    receipt["receipt_sha256"] = verified_worker_receipt_sha256(receipt)
    return receipt


def _blocked_visible(spec: WorkerTaskSpec, client: ModelClient, reason: str) -> WorkerResult:
    receipt: dict[str, Any] = {
        "task_id": spec.task_id,
        "task_sha256": spec.sha256,
        "base_head_sha": spec.base_head_sha,
        "source_snapshot_sha256": spec.source_snapshot_sha256,
        "model_provider": client.provider,
        "requested_model": client.model,
        "resolved_model": None,
        "status": "BLOCKED",
        "reason": reason,
        "changed_paths": [],
        "candidate_changed_paths": [],
        "candidate_patch_sha256": None,
        "receipt_sha256": sha256_json({"blocked_before_model": reason, "task_sha256": spec.sha256}),
    }
    return WorkerResult(receipt=receipt, patch="")


def _finish(
    visible: WorkerResult,
    oracle: HiddenOracle,
    hidden: dict[str, Any],
    *,
    status: str,
    reason: str,
    patch: str,
) -> VerifiedWorkerResult:
    delivered_patch = patch if status == "PASS" else ""
    visible_receipt = visible.receipt
    value: dict[str, Any] = {
        "schema_version": VERIFIED_WORKER_RECEIPT_SCHEMA_VERSION,
        "task_id": visible_receipt["task_id"],
        "task_sha256": visible_receipt["task_sha256"],
        "base_head_sha": visible_receipt["base_head_sha"],
        "source_snapshot_sha256": visible_receipt["source_snapshot_sha256"],
        "model_provider": visible_receipt["model_provider"],
        "requested_model": visible_receipt["requested_model"],
        "resolved_model": visible_receipt["resolved_model"],
        "visible_status": visible_receipt["status"],
        "visible_receipt_sha256": visible_receipt["receipt_sha256"],
        "hidden_oracle": hidden,
        "status": status,
        "reason": reason,
        "candidate_changed_paths": visible_receipt.get("candidate_changed_paths", []),
        "candidate_patch_sha256": visible_receipt.get("candidate_patch_sha256"),
        "changed_paths": visible_receipt["changed_paths"] if status == "PASS" else [],
        "patch_sha256": sha256_bytes(delivered_patch.encode("utf-8")) if delivered_patch else None,
        "patch_delivered": status == "PASS",
        "oracle_manifest_sha256": oracle.manifest_sha256,
        "commit_allowed": False,
        "push_allowed": False,
        "merge_allowed": False,
        "production_allowed": False,
        "independent_audit_required": True,
    }
    receipt = _sealed(value)
    problems = validate_verified_worker_receipt(receipt, delivered_patch)
    if problems:
        raise RuntimeError(f"internal verified Worker receipt invariant failed: {problems}")
    return VerifiedWorkerResult(receipt, delivered_patch)


def _oracle_failure_status(reason: str) -> str:
    if "DRIFT" in reason or "DIGEST_MISMATCH" in reason:
        return "FAIL"
    return "BLOCKED"


def _assert_oracle_boundary(repo_path: Path, oracle: HiddenOracle) -> None:
    assert_hidden_oracle_external(repo_path, oracle)
    oracle.assert_pinned()


def run_verified_worker(
    repo_path: Path,
    spec: WorkerTaskSpec,
    client: ModelClient,
    oracle: HiddenOracle,
    *,
    work_parent: Path | None = None,
) -> VerifiedWorkerResult:
    try:
        _assert_oracle_boundary(repo_path, oracle)
    except OracleError as exc:
        visible = _blocked_visible(spec, client, str(exc))
        return _finish(
            visible,
            oracle,
            hidden_oracle_not_run(oracle),
            status=_oracle_failure_status(str(exc)),
            reason=str(exc),
            patch="",
        )

    visible = run_worker(repo_path, spec, client, work_parent=work_parent)
    if visible.receipt["status"] != "PASS":
        return _finish(
            visible,
            oracle,
            hidden_oracle_not_run(oracle),
            status=visible.receipt["status"],
            reason=f"VISIBLE_{visible.receipt['reason']}",
            patch="",
        )

    try:
        _assert_oracle_boundary(repo_path, oracle)
        identity = verify_source_repository(repo_path, spec)
        temporary_parent = None if work_parent is None else str(work_parent)
        with tempfile.TemporaryDirectory(prefix="programming-agent-hidden-", dir=temporary_parent) as temporary:
            candidate = Path(temporary) / "candidate"
            create_disposable_workspace(repo_path, candidate, identity)
            replay_cumulative_patch(candidate, visible.patch)
            command_workspace = Path(temporary) / "commands"
            copy_candidate_for_commands(candidate, command_workspace)
            hidden_result = run_hidden_oracle(command_workspace, oracle).to_dict()
        _assert_oracle_boundary(repo_path, oracle)
    except (OracleError, WorkspaceError) as exc:
        return _finish(
            visible,
            oracle,
            hidden_oracle_not_run(oracle),
            status=_oracle_failure_status(str(exc)),
            reason=str(exc),
            patch="",
        )

    hidden_pass = hidden_result["status"] == "PASS"
    if not oracle_gate_passes(True, hidden_pass, True):
        return _finish(
            visible,
            oracle,
            hidden_result,
            status=hidden_result["status"],
            reason=hidden_result["reason"],
            patch="",
        )
    return _finish(
        visible,
        oracle,
        hidden_result,
        status="PASS",
        reason="VISIBLE_AND_HIDDEN_ACCEPTANCE_PASSED",
        patch=visible.patch,
    )


def validate_verified_worker_receipt(receipt: Any, patch: str) -> list[str]:
    problems: list[str] = []
    if not isinstance(receipt, dict):
        return ["VERIFIED_RECEIPT_NOT_OBJECT"]
    if receipt.get("schema_version") != VERIFIED_WORKER_RECEIPT_SCHEMA_VERSION:
        problems.append("VERIFIED_SCHEMA_VERSION_INVALID")
    hidden = receipt.get("hidden_oracle")
    if not isinstance(hidden, dict) or set(hidden) != _HIDDEN_FIELDS:
        problems.append("HIDDEN_ORACLE_SUMMARY_INVALID")
        hidden = {}
    for field in ("oracle_manifest_sha256", "visible_receipt_sha256", "receipt_sha256"):
        value = receipt.get(field)
        if not isinstance(value, str) or _HEX64.fullmatch(value) is None:
            problems.append(f"{field.upper()}_INVALID")
    if hidden.get("manifest_sha256") != receipt.get("oracle_manifest_sha256"):
        problems.append("HIDDEN_ORACLE_MANIFEST_BINDING_MISMATCH")
    for forbidden in ("argv", "stdout", "stderr", "path", "command", "commands"):
        if forbidden in hidden:
            problems.append("HIDDEN_ORACLE_SECRET_FIELD_LEAK")
    for field in ("commit_allowed", "push_allowed", "merge_allowed", "production_allowed"):
        if receipt.get(field) is not False:
            problems.append(f"{field.upper()}_MUST_BE_FALSE")
    if receipt.get("independent_audit_required") is not True:
        problems.append("INDEPENDENT_AUDIT_REQUIRED_MUST_BE_TRUE")
    status = receipt.get("status")
    if status not in ("PASS", "FAIL", "BLOCKED"):
        problems.append("VERIFIED_STATUS_INVALID")
    delivered = receipt.get("patch_delivered")
    if status == "PASS":
        if delivered is not True or not patch:
            problems.append("VERIFIED_PASS_WITHOUT_PATCH")
        if receipt.get("visible_status") != "PASS" or hidden.get("status") != "PASS":
            problems.append("VERIFIED_PASS_WITHOUT_ALL_GATES")
        if receipt.get("patch_sha256") != sha256_bytes(patch.encode("utf-8")):
            problems.append("VERIFIED_PATCH_SHA256_MISMATCH")
    elif delivered is not False or patch or receipt.get("patch_sha256") is not None or receipt.get("changed_paths"):
        problems.append("VERIFIED_NONPASS_DELIVERED_PATCH")
    digest = receipt.get("receipt_sha256")
    if isinstance(digest, str) and _HEX64.fullmatch(digest) and verified_worker_receipt_sha256(receipt) != digest:
        problems.append("VERIFIED_RECEIPT_SHA256_MISMATCH")
    return problems
