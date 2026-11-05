from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .hashutil import sha256_bytes, sha256_json, strict_json_loads
from . import programming_quality as q
from .worker_commands import run_acceptance_suite
from .worker_oracle import HiddenOracle
from .worker_spec import AcceptanceCommand, WorkerTaskSpec
from .worker_workspace import WorkspaceError, create_disposable_workspace, verify_source_repository

READBACK_SCHEMA_VERSION = 1
SEMANTIC_RISKS = {
    "concurrency", "atomicity", "idempotency", "retries",
    "partial_failures", "external_side_effects",
}
SEMANTIC_HIDDEN_FAMILY = "concurrency_partial_failure"
REQUIRED_TEST007_HOLDOUTS = {
    "test007_concurrent_duplicate_effect",
    "test007_partial_failure_retry",
}
_ALLOWED_TYPES: dict[str, type[Any] | None] = {
    "str": str, "int": int, "float": float, "bool": bool,
    "list": list, "dict": dict, "null": None,
}
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class ReadbackManifest:
    task_id: str
    checks: tuple[dict[str, Any], ...]
    not_applicable_reason: str | None
    sha256: str


def parse_readback_manifest(value: Any) -> ReadbackManifest:
    top = {"schema_version", "task_id", "checks", "not_applicable_reason"}
    if not isinstance(value, dict) or set(value) != top:
        raise ValueError(f"readback manifest fields must be exactly {sorted(top)}")
    if type(value["schema_version"]) is not int or value["schema_version"] != READBACK_SCHEMA_VERSION:
        raise ValueError("readback schema_version must be 1")
    task_id = value["task_id"]
    if not isinstance(task_id, str) or not task_id or len(task_id.encode()) > 128:
        raise ValueError("readback task_id is invalid")
    checks = value["checks"]
    reason = value["not_applicable_reason"]
    if not isinstance(checks, list):
        raise ValueError("readback checks must be an array")
    if checks and reason is not None:
        raise ValueError("not_applicable_reason must be null when checks exist")
    if not checks and (not isinstance(reason, str) or len(reason.strip()) < 12):
        raise ValueError("empty readback requires an explicit not-applicable reason")
    fields = {
        "entity", "expected_entity", "row", "pk_field", "expected_pk",
        "field", "expected_value", "expected_type", "status_field", "expected_status",
    }
    normalized: list[dict[str, Any]] = []
    for index, check in enumerate(checks):
        if not isinstance(check, dict) or set(check) != fields:
            raise ValueError(f"readback checks[{index}] fields are invalid")
        if not isinstance(check["row"], dict) or check["expected_type"] not in _ALLOWED_TYPES:
            raise ValueError(f"readback checks[{index}] row/type is invalid")
        for field in ("entity", "expected_entity", "pk_field", "field"):
            if not isinstance(check[field], str) or not check[field]:
                raise ValueError(f"readback checks[{index}].{field} is invalid")
        if check["status_field"] is not None and not isinstance(check["status_field"], str):
            raise ValueError(f"readback checks[{index}].status_field is invalid")
        normalized.append(dict(check))
    payload = {key: value[key] for key in sorted(top)}
    return ReadbackManifest(task_id, tuple(normalized), None if checks else reason.strip(), sha256_json(payload))


def load_readback_manifest(path: Path, expected_sha256: str) -> ReadbackManifest:
    if _HEX64.fullmatch(expected_sha256) is None:
        raise ValueError("readback expected_sha256 is invalid")
    data = path.read_bytes()
    observed = sha256_bytes(data)
    if observed != expected_sha256:
        raise ValueError(f"READBACK_MANIFEST_DIGEST_MISMATCH: expected {expected_sha256}, observed {observed}")
    try:
        value = strict_json_loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"readback manifest JSON invalid: {type(exc).__name__}") from exc
    return parse_readback_manifest(value)


def coverage_inventory(spec: WorkerTaskSpec, oracle: HiddenOracle) -> set[tuple[str, str]]:
    refs = {("acceptance_test", f"acceptance:{cmd.name}") for cmd in spec.acceptance_commands}
    refs.update(("hidden_adversarial_test", f"hidden:{cmd.name}") for cmd in oracle.commands)
    refs.add(("hidden_adversarial_test", f"hidden-family:{oracle.family}:{oracle.version}"))
    refs.add(("architecture_judge", "control:SEMANTIC_POST_GREEN_JUDGE"))
    refs.add(("security_judge", "control:EXISTING_SECURITY_GATE"))
    return refs


def evaluate_bound_risk_profile(
    plan: q.QualityPlan, spec: WorkerTaskSpec, oracle: HiddenOracle, *, execution_id: str,
) -> dict[str, Any]:
    inventory = coverage_inventory(spec, oracle)
    invalid = [
        {"dimension": entry["dimension"], **binding}
        for entry in plan.risk_profile if entry["classification"] == "APPLIES"
        for binding in entry["coverage"] if (binding["kind"], binding["ref"]) not in inventory
    ]
    return q._control_receipt(
        "RISK_PROFILE_PRE_EXEC", task_id=plan.task_id, execution_id=execution_id,
        head_sha=plan.base_head_sha,
        input_digest=sha256_json({"plan": plan.sha256, "inventory": sorted(inventory)}),
        outcome="FAIL" if invalid else "PASS",
        reason_code="COVERAGE_REFERENCE_UNVERIFIED" if invalid else "ALL_APPLICABLE_RISKS_BOUND_AND_VERIFIED",
        evidence_refs=[f"{kind}:{ref}" for kind, ref in sorted(inventory)],
        details={"invalid_bindings": invalid},
    )


def validate_hidden_holdout_contract(
    plan: q.QualityPlan, oracle: HiddenOracle, baseline: Mapping[str, Any]
) -> list[str]:
    findings: list[str] = []
    families = baseline.get("families", {})
    if oracle.family not in families:
        return ["HIDDEN_ORACLE_FAMILY_NOT_BASELINED"]
    required_count = families[oracle.family]["min_hidden_holdouts"]
    if len(oracle.commands) < required_count:
        findings.append("HIDDEN_HOLDOUT_COUNT_BELOW_BASELINE")
    applicable = {e["dimension"] for e in plan.risk_profile if e["classification"] == "APPLIES"}
    if applicable & SEMANTIC_RISKS:
        if oracle.family != SEMANTIC_HIDDEN_FAMILY:
            findings.append("TEST007_HIDDEN_FAMILY_REQUIRED")
        names = {cmd.name for cmd in oracle.commands}
        for required in sorted(REQUIRED_TEST007_HOLDOUTS):
            if required not in names:
                findings.append(f"HIDDEN_HOLDOUT_MISSING:{required}")
        if not plan.semantic_paths:
            findings.append("SEMANTIC_TARGETS_REQUIRED")
    return findings


def hidden_contract_receipt(plan: q.QualityPlan, oracle: HiddenOracle, baseline: Mapping[str, Any], *, execution_id: str) -> dict[str, Any]:
    findings = validate_hidden_holdout_contract(plan, oracle, baseline)
    return q._control_receipt(
        "HIDDEN_HOLDOUT_BASELINE", task_id=plan.task_id, execution_id=execution_id,
        head_sha=plan.base_head_sha,
        input_digest=sha256_json({
            "baseline": baseline["baseline_id"], "oracle_family": oracle.family,
            "oracle_version": oracle.version, "oracle_manifest": oracle.manifest_sha256,
            "commands": sorted(cmd.name for cmd in oracle.commands),
        }),
        outcome="FAIL" if findings else "PASS",
        reason_code="HIDDEN_HOLDOUT_BASELINE_VIOLATION" if findings else "HIDDEN_HOLDOUT_BASELINE_ENFORCED",
        evidence_refs=[f"oracle:{oracle.family}:{oracle.version}:{oracle.manifest_sha256}"],
        details={"findings": findings, "command_count": len(oracle.commands)},
    )


def _meaningful(command: AcceptanceCommand, stage: str) -> bool:
    joined = " ".join(command.argv).lower()
    if joined.strip() in {"true", "/bin/true", "python -c pass", "python3 -c pass"}:
        return False
    if "exit(0)" in joined or "sys.exit(0)" in joined:
        return False
    return ("import" in joined or "pytest" in joined or "unittest" in joined) if stage == "setup_import" else (
        "assert" in joined or "pytest" in joined or "unittest" in joined or "test" in joined
    )


def run_canonical_fixture_preflight(workspace: Path, plan: q.QualityPlan, *, execution_id: str) -> dict[str, Any]:
    stages: list[dict[str, Any]] = []
    errors: list[str] = []
    files = [p for p in workspace.rglob("*.py") if ".git" not in p.parts and "__pycache__" not in p.parts]
    for path in files:
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=path.relative_to(workspace).as_posix())
        except (OSError, UnicodeError, SyntaxError) as exc:
            errors.append(f"{path.relative_to(workspace).as_posix()}:{type(exc).__name__}")
    stages.append({"name": "parse_compile", "status": "FAIL" if errors else "PASS", "errors": errors})
    if not errors:
        argv = (sys.executable, "tools/lint.py") if (workspace / "tools/lint.py").is_file() else (sys.executable, "-m", "ruff", "check", ".")
        result = subprocess.run(argv, cwd=workspace, check=False, capture_output=True, text=True)
        stages.append({"name": "lint_static", "status": "PASS" if result.returncode == 0 else "FAIL", "returncode": result.returncode})
    for index, stage in ((2, "setup_import"), (3, "reachability")):
        if all(item["status"] == "PASS" for item in stages):
            command = plan.fixture_preflight_commands[index]
            if not _meaningful(command, stage):
                stages.append({"name": stage, "status": "FAIL", "reason": "STAGE_COMMAND_NOT_MEANINGFUL"})
            else:
                results = run_acceptance_suite(workspace, (command,))
                status = results[0].status if len(results) == 1 else "FAIL"
                stages.append({"name": stage, "status": status, "reason": results[0].reason if len(results) == 1 else "INCOMPLETE"})
    passed = len(stages) == 4 and all(item["status"] == "PASS" for item in stages)
    return q._control_receipt(
        "FIXTURE_PREFLIGHT", task_id=plan.task_id, execution_id=execution_id,
        head_sha=plan.base_head_sha, input_digest=sha256_json({"plan": plan.sha256, "stages": stages}),
        outcome="PASS" if passed else "FAIL", reason_code="FIXTURE_VALID" if passed else "FIXTURE_INVALID",
        evidence_refs=[f"fixture:{item['name']}:{item['status']}" for item in stages], details={"stages": stages},
    )


def run_readback_gate(manifest: ReadbackManifest, plan: q.QualityPlan, *, execution_id: str) -> dict[str, Any]:
    if manifest.task_id != plan.task_id:
        return q._control_receipt(
            "READBACK_FIELD_BINDING", task_id=plan.task_id, execution_id=execution_id,
            head_sha=plan.base_head_sha, input_digest=manifest.sha256, outcome="FAIL",
            reason_code="READBACK_TASK_BINDING_MISMATCH", details={"manifest_task_id": manifest.task_id},
        )
    if not manifest.checks:
        return q._control_receipt(
            "READBACK_FIELD_BINDING", task_id=plan.task_id, execution_id=execution_id,
            head_sha=plan.base_head_sha, input_digest=manifest.sha256, outcome="N/A",
            reason_code="READBACK_EXPLICITLY_NOT_APPLICABLE", details={"justification": manifest.not_applicable_reason},
        )
    children = [q.readback_field_binding(
        entity=c["entity"], expected_entity=c["expected_entity"], row=c["row"], pk_field=c["pk_field"],
        expected_pk=c["expected_pk"], field=c["field"], expected_value=c["expected_value"],
        expected_type=_ALLOWED_TYPES[c["expected_type"]], status_field=c["status_field"], expected_status=c["expected_status"],
        task_id=plan.task_id, execution_id=f"{execution_id}:readback:{i}", head_sha=plan.base_head_sha,
    ) for i, c in enumerate(manifest.checks)]
    failures = [item for item in children if item["outcome"] != "PASS"]
    return q._control_receipt(
        "READBACK_FIELD_BINDING", task_id=plan.task_id, execution_id=execution_id,
        head_sha=plan.base_head_sha, input_digest=manifest.sha256,
        outcome="FAIL" if failures else "PASS",
        reason_code="READBACK_EXACT_FIELD_MISMATCH" if failures else "READBACK_ALL_EXACT_FIELDS_MATCH",
        evidence_refs=[f"readback:{item['output_digest']}" for item in children],
        details={"check_count": len(children), "failed_count": len(failures)},
    )


def _outer_receipt(
    plan: q.QualityPlan, spec: WorkerTaskSpec, controls: list[dict[str, Any]],
    legacy: q.ProgrammingQualityWorkerResult | None, *, status: str, reason: str, patch: str,
) -> q.ProgrammingQualityWorkerResult:
    value: dict[str, Any] = {
        "schema_version": 2, "task_id": plan.task_id, "task_sha256": spec.sha256,
        "base_head_sha": plan.base_head_sha, "source_snapshot_sha256": spec.source_snapshot_sha256,
        "quality_plan_sha256": plan.sha256,
        "controls": [{"control_id": c["control_id"], "outcome": c["outcome"], "reason_code": c["reason_code"], "output_digest": c["output_digest"]} for c in controls],
        "legacy_quality_receipt_sha256": None if legacy is None else legacy.receipt["receipt_sha256"],
        "status": status, "reason": reason,
        "patch_sha256": sha256_bytes(patch.encode()) if patch else None,
        "patch_delivered": status == "PASS", "commit_allowed": False, "push_allowed": False,
        "merge_allowed": False, "production_allowed": False, "independent_audit_required": True,
    }
    value["receipt_sha256"] = sha256_json(value)
    return q.ProgrammingQualityWorkerResult(value, patch if status == "PASS" else "")


def run_programming_quality_worker_hardened(
    repo_path: Path, spec: WorkerTaskSpec, client: Any, oracle: HiddenOracle,
    plan: q.QualityPlan, readback_manifest: ReadbackManifest, *, work_parent: Path | None = None,
) -> q.ProgrammingQualityWorkerResult:
    execution = plan.task_id
    if plan.task_id != spec.task_id or plan.base_head_sha != spec.base_head_sha:
        return _outer_receipt(plan, spec, [], None, status="BLOCKED", reason="QUALITY_PLAN_TASK_BINDING_MISMATCH", patch="")
    try:
        baseline = q.load_baseline(repo_path / "quality/programming_quality/baseline_v1.json")
    except ValueError as exc:
        return _outer_receipt(plan, spec, [], None, status="BLOCKED", reason=f"BASELINE_INVALID:{exc}", patch="")
    controls = [evaluate_bound_risk_profile(plan, spec, oracle, execution_id=execution)]
    controls.append(hidden_contract_receipt(plan, oracle, baseline, execution_id=execution))
    controls.append(run_readback_gate(readback_manifest, plan, execution_id=execution))
    if any(c["outcome"] == "FAIL" for c in controls):
        return _outer_receipt(plan, spec, controls, None, status="BLOCKED", reason=next(c["reason_code"] for c in controls if c["outcome"] == "FAIL"), patch="")
    try:
        identity = verify_source_repository(repo_path, spec)
        parent = None if work_parent is None else str(work_parent)
        with tempfile.TemporaryDirectory(prefix="programming-agent-hardened-preflight-", dir=parent) as temporary:
            workspace = Path(temporary) / "fixture"
            create_disposable_workspace(repo_path, workspace, identity)
            fixture = run_canonical_fixture_preflight(workspace, plan, execution_id=execution)
    except WorkspaceError as exc:
        fixture = q._control_receipt(
            "FIXTURE_PREFLIGHT", task_id=plan.task_id, execution_id=execution,
            head_sha=plan.base_head_sha, input_digest=plan.sha256, outcome="BLOCKED", reason_code=str(exc),
        )
    controls.append(fixture)
    if fixture["outcome"] != "PASS":
        return _outer_receipt(plan, spec, controls, None, status="BLOCKED", reason=fixture["reason_code"], patch="")
    legacy = q.run_programming_quality_worker(repo_path, spec, client, oracle, plan, work_parent=work_parent, execution_id=execution)
    if legacy.receipt["status"] != "PASS":
        return _outer_receipt(plan, spec, controls, legacy, status=legacy.receipt["status"], reason=legacy.receipt["reason"], patch="")
    return _outer_receipt(plan, spec, controls, legacy, status="PASS", reason="HARDENED_PROGRAMMING_QUALITY_GATE_PASSED", patch=legacy.patch)


load_quality_plan = q.load_quality_plan
