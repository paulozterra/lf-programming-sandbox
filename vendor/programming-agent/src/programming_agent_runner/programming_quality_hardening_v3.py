from __future__ import annotations

import ast
import subprocess
import sys
import tempfile
import urllib.error
from pathlib import Path
from typing import Any, Mapping

from . import programming_quality as q
from . import programming_quality_hardening_v2 as v2
from .hashutil import sha256_bytes, sha256_json
from .worker_commands import run_acceptance_suite
from .worker_oracle import HiddenOracle
from .worker_spec import AcceptanceCommand, WorkerTaskSpec
from .worker_workspace import WorkspaceError, create_disposable_workspace, replay_cumulative_patch, verify_source_repository

SEMANTIC_RISKS = v2.SEMANTIC_RISKS
SEMANTIC_HIDDEN_FAMILY = v2.SEMANTIC_HIDDEN_FAMILY
REQUIRED_TEST007_HOLDOUTS = v2.REQUIRED_TEST007_HOLDOUTS
_STRONG_GUARDS = {"claim_once", "compare_and_set", "insert_if_absent"}
_READS = {"get", "load", "lookup", "find", "exists", "is_processed"}
_SAVES = {"save", "persist", "mark_processed", "update", "insert", "commit", "set_processed"}
_EFFECTS = {"charge", "debit", "transfer", "send", "publish", "dispatch", "create_payment", "capture"}
_PURE_CALLS = {
    "len", "str", "int", "float", "bool", "dict", "list", "set", "tuple",
    "min", "max", "sum", "sorted", "enumerate", "range", "isinstance",
}

ReadbackManifest = v2.ReadbackManifest
parse_readback_manifest = v2.parse_readback_manifest
load_readback_manifest = v2.load_readback_manifest
readback_source_paths = v2.readback_source_paths
load_execution_evidence_config = v2.load_execution_evidence_config
evaluate_ci_execution_evidence = v2.evaluate_ci_execution_evidence
load_quality_plan = q.load_quality_plan


def _call_name(call: ast.Call) -> str:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return ""


def _inline_python(command: AcceptanceCommand) -> ast.AST | None:
    argv = list(command.argv)
    try:
        index = argv.index("-c")
    except ValueError:
        return None
    if index + 1 >= len(argv):
        return None
    try:
        return ast.parse(argv[index + 1])
    except SyntaxError:
        return None


def _imported_modules(tree: ast.AST) -> set[str]:
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def _call_tokens(tree: ast.AST) -> set[str]:
    return {_call_name(node).lower() for node in ast.walk(tree) if isinstance(node, ast.Call) and _call_name(node)}


def _semantic_target_roots(plan: q.QualityPlan) -> set[str]:
    roots: set[str] = set()
    for relative in plan.semantic_paths:
        parts = list(Path(relative).with_suffix("").parts)
        if parts and parts[0] == "src":
            parts = parts[1:]
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        if parts:
            roots.add(parts[0])
            roots.add(".".join(parts))
    return roots


def _nonconstant_assert_count(tree: ast.AST) -> int:
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, ast.Assert)
        and not (isinstance(node.test, ast.Constant) and node.test.value in (True, 1))
    )


def validate_test007_command_semantics(plan: q.QualityPlan, oracle: HiddenOracle) -> list[str]:
    if oracle.family != SEMANTIC_HIDDEN_FAMILY:
        return []
    by_name = {command.name: command for command in oracle.commands}
    targets = _semantic_target_roots(plan)
    target_roots = {item.split(".")[0] for item in targets}
    findings: list[str] = []
    for required in sorted(REQUIRED_TEST007_HOLDOUTS):
        command = by_name.get(required)
        if command is None:
            findings.append(f"HIDDEN_HOLDOUT_MISSING:{required}")
            continue
        tree = _inline_python(command)
        if tree is None:
            findings.append(f"HIDDEN_HOLDOUT_SOURCE_NOT_PINNED_INLINE:{required}")
            continue
        imports = _imported_modules(tree)
        imported_roots = {item.split(".")[0] for item in imports}
        if not (imports & targets or imported_roots & target_roots):
            findings.append(f"HIDDEN_HOLDOUT_NOT_BOUND_TO_SEMANTIC_TARGET:{required}")
        if _nonconstant_assert_count(tree) < 1:
            findings.append(f"HIDDEN_HOLDOUT_ASSERTION_MISSING:{required}")
        tokens = _call_tokens(tree)
        if required == "test007_concurrent_duplicate_effect":
            concurrency = {"thread", "barrier", "threadpoolexecutor", "submit", "start", "join"}
            if not ({"threading", "concurrent"} & imported_roots) or len(tokens & concurrency) < 2:
                findings.append("HIDDEN_HOLDOUT_CONCURRENCY_BEHAVIOR_UNPROVEN")
        else:
            failure = {"retry", "process", "fail", "save", "persist", "charge", "capture"}
            has_failure_control = any(isinstance(node, (ast.Try, ast.Raise)) for node in ast.walk(tree))
            if not has_failure_control or len(tokens & failure) < 2:
                findings.append("HIDDEN_HOLDOUT_PARTIAL_FAILURE_BEHAVIOR_UNPROVEN")
    return sorted(set(findings))


def validate_hidden_holdout_contract(
    plan: q.QualityPlan,
    oracle: HiddenOracle,
    baseline: Mapping[str, Any],
) -> list[str]:
    families = baseline.get("families", {})
    if oracle.family not in families:
        return ["HIDDEN_ORACLE_FAMILY_NOT_BASELINED"]
    findings: list[str] = []
    if len(oracle.commands) < families[oracle.family]["min_hidden_holdouts"]:
        findings.append("HIDDEN_HOLDOUT_COUNT_BELOW_BASELINE")
    applies = {
        entry["dimension"]
        for entry in plan.risk_profile
        if entry["classification"] == "APPLIES"
    }
    if applies & SEMANTIC_RISKS:
        if oracle.family != SEMANTIC_HIDDEN_FAMILY:
            findings.append("TEST007_HIDDEN_FAMILY_REQUIRED")
        if not plan.semantic_paths:
            findings.append("SEMANTIC_TARGETS_REQUIRED")
        findings.extend(validate_test007_command_semantics(plan, oracle))
    return sorted(set(findings))


def hidden_contract_receipt(
    plan: q.QualityPlan,
    oracle: HiddenOracle,
    baseline: Mapping[str, Any],
    *,
    execution_id: str,
) -> dict[str, Any]:
    findings = validate_hidden_holdout_contract(plan, oracle, baseline)
    return q._control_receipt(
        "HIDDEN_HOLDOUT_BEHAVIORAL_CONTRACT",
        task_id=plan.task_id,
        execution_id=execution_id,
        head_sha=plan.base_head_sha,
        input_digest=sha256_json({
            "baseline": baseline["baseline_id"],
            "oracle_manifest": oracle.manifest_sha256,
            "commands": [sha256_json(command.to_dict()) for command in oracle.commands],
        }),
        outcome="FAIL" if findings else "PASS",
        reason_code="HIDDEN_HOLDOUT_BEHAVIOR_UNPROVEN" if findings else "HIDDEN_HOLDOUT_BEHAVIOR_PROVEN",
        evidence_refs=[f"oracle:{oracle.family}:{oracle.version}:{oracle.manifest_sha256}"],
        details={"findings": findings, "command_count": len(oracle.commands)},
    )


def _strong_semantic_findings(text: str, path: str) -> list[dict[str, Any]]:
    tree = ast.parse(text, filename=path)
    findings: list[dict[str, Any]] = []
    scopes: list[ast.AST] = [tree]
    scopes.extend(
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    )
    seen: set[tuple[int, str]] = set()
    for scope in scopes:
        calls = sorted(
            (node for node in ast.walk(scope) if isinstance(node, ast.Call)),
            key=lambda node: (getattr(node, "lineno", 0), getattr(node, "col_offset", 0)),
        )
        names = [_call_name(call) for call in calls]
        for save_index, save_name in enumerate(names):
            if save_name not in _SAVES:
                continue
            reads = [index for index, name in enumerate(names[:save_index]) if name in _READS]
            if not reads:
                continue
            read_index = reads[-1]
            between = list(zip(calls[read_index + 1:save_index], names[read_index + 1:save_index]))
            strong_guard = any(name in _STRONG_GUARDS for _, name in between)
            for call, name in between:
                if name in _READS or name in _SAVES or name in _STRONG_GUARDS or name in _PURE_CALLS:
                    continue
                line = getattr(call, "lineno", 0)
                if isinstance(call.func, ast.Attribute) and name not in _EFFECTS:
                    key = (line, "UNCLASSIFIED_EFFECT_BETWEEN_READ_SAVE")
                    if key not in seen:
                        findings.append({
                            "code": key[1],
                            "path": path,
                            "line": line,
                            "detail": f"unclassified call {name!r} between read/check and durable save",
                        })
                        seen.add(key)
                if name in _EFFECTS and not strong_guard:
                    for code in (
                        "RACE_GET_EFFECT_SAVE",
                        "PARTIAL_FAILURE_EFFECT_BEFORE_DURABLE_STATE",
                    ):
                        key = (line, code)
                        if key not in seen:
                            findings.append({
                                "code": code,
                                "path": path,
                                "line": line,
                                "detail": "external effect lacks proven strong atomic guard before durable state",
                            })
                            seen.add(key)
    return findings


def conservative_semantic_gate(
    root: Path,
    plan: q.QualityPlan,
    *,
    execution_id: str,
) -> dict[str, Any]:
    applies = {
        entry["dimension"]
        for entry in plan.risk_profile
        if entry["classification"] == "APPLIES"
    }
    if not (applies & SEMANTIC_RISKS):
        return q._control_receipt(
            "SEMANTIC_BEHAVIORAL_GUARD",
            task_id=plan.task_id,
            execution_id=execution_id,
            head_sha=plan.base_head_sha,
            input_digest=plan.sha256,
            outcome="N/A",
            reason_code="NO_APPLICABLE_NONFUNCTIONAL_RISK",
        )
    if not plan.semantic_paths:
        return q._control_receipt(
            "SEMANTIC_BEHAVIORAL_GUARD",
            task_id=plan.task_id,
            execution_id=execution_id,
            head_sha=plan.base_head_sha,
            input_digest=plan.sha256,
            outcome="FAIL",
            reason_code="SEMANTIC_TARGETS_REQUIRED",
        )
    findings: list[dict[str, Any]] = []
    digests: dict[str, str] = {}
    try:
        for relative in plan.semantic_paths:
            target = root / relative
            if not target.is_file():
                raise WorkspaceError(f"SEMANTIC_TARGET_MISSING:{relative}")
            text = target.read_text(encoding="utf-8")
            digests[relative] = sha256_bytes(text.encode("utf-8"))
            findings.extend(_strong_semantic_findings(text, relative))
    except (OSError, UnicodeError, SyntaxError, WorkspaceError) as exc:
        return q._control_receipt(
            "SEMANTIC_BEHAVIORAL_GUARD",
            task_id=plan.task_id,
            execution_id=execution_id,
            head_sha=plan.base_head_sha,
            input_digest=sha256_json({"plan": plan.sha256, "digests": digests}),
            outcome="BLOCKED",
            reason_code=f"SEMANTIC_BEHAVIORAL_GUARD_BLOCKED:{exc}",
        )
    return q._control_receipt(
        "SEMANTIC_BEHAVIORAL_GUARD",
        task_id=plan.task_id,
        execution_id=execution_id,
        head_sha=plan.base_head_sha,
        input_digest=sha256_json({"plan": plan.sha256, "digests": digests}),
        outcome="FAIL" if findings else "PASS",
        reason_code="SEMANTIC_BEHAVIORAL_RISK_DETECTED" if findings else "SEMANTIC_BEHAVIORAL_GUARD_PASSED",
        evidence_refs=[f"semantic-v3:{item['path']}:{item['line']}:{item['code']}" for item in findings],
        details={"findings": findings},
    )


def _workspace_module_tokens(workspace: Path) -> set[str]:
    tokens: set[str] = set()
    for path in workspace.rglob("*.py"):
        if ".git" in path.parts or "__pycache__" in path.parts:
            continue
        relative = path.relative_to(workspace)
        if relative.parts and relative.parts[0] in {"tools", "tests"}:
            continue
        parts = list(relative.with_suffix("").parts)
        if parts and parts[0] == "src":
            parts = parts[1:]
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        if parts:
            tokens.add(parts[0])
            tokens.add(".".join(parts))
        tokens.add(path.stem)
    return {token for token in tokens if token and token != "__init__"}


def _fixture_stage_semantic(
    command: AcceptanceCommand,
    stage: str,
    workspace: Path,
) -> tuple[bool, str]:
    joined = " ".join(command.argv).lower()
    if (
        joined.strip() in {"true", "/bin/true", "python -c pass", "python3 -c pass"}
        or "exit(0)" in joined
        or "sys.exit(0)" in joined
    ):
        return False, "STAGE_COMMAND_NOOP"
    targets = _workspace_module_tokens(workspace)
    tree = _inline_python(command)
    if tree is None:
        runner = "pytest" in joined or "unittest" in joined
        bound = any(token.lower() in joined for token in targets if len(token) >= 3)
        return (
            runner and bound,
            "STAGE_TEST_RUNNER_BOUND" if runner and bound else "STAGE_COMMAND_NOT_REPOSITORY_BOUND",
        )
    imports = _imported_modules(tree)
    imported_roots = {item.split(".")[0] for item in imports}
    target_roots = {item.split(".")[0] for item in targets}
    bound_names = imported_roots & target_roots
    bound = bool(imports & targets or bound_names)
    if stage == "setup_import":
        return bound, "STAGE_IMPORT_BOUND" if bound else "STAGE_IMPORT_NOT_REPOSITORY_BOUND"
    assertion_bound = False
    for assertion in (node for node in ast.walk(tree) if isinstance(node, ast.Assert)):
        for nested in ast.walk(assertion.test):
            if not isinstance(nested, ast.Call):
                continue
            func = nested.func
            if (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id in bound_names
            ):
                assertion_bound = True
    return (
        bound and assertion_bound,
        "STAGE_REACHABILITY_BOUND" if bound and assertion_bound else "STAGE_REACHABILITY_NOT_REPOSITORY_BOUND",
    )


def run_canonical_fixture_preflight(
    workspace: Path,
    plan: q.QualityPlan,
    *,
    execution_id: str,
) -> dict[str, Any]:
    stages: list[dict[str, Any]] = []
    errors: list[str] = []
    for path in (
        item
        for item in workspace.rglob("*.py")
        if ".git" not in item.parts and "__pycache__" not in item.parts
    ):
        try:
            ast.parse(
                path.read_text(encoding="utf-8"),
                filename=path.relative_to(workspace).as_posix(),
            )
        except (OSError, UnicodeError, SyntaxError) as exc:
            errors.append(f"{path.relative_to(workspace).as_posix()}:{type(exc).__name__}")
    stages.append({"name": "parse_compile", "status": "FAIL" if errors else "PASS", "errors": errors})
    if not errors:
        argv = (
            (sys.executable, "tools/lint.py")
            if (workspace / "tools/lint.py").is_file()
            else (sys.executable, "-m", "ruff", "check", ".")
        )
        result = subprocess.run(argv, cwd=workspace, check=False, capture_output=True, text=True)
        stages.append({
            "name": "lint_static",
            "status": "PASS" if result.returncode == 0 else "FAIL",
            "returncode": result.returncode,
        })
    for index, stage in ((2, "setup_import"), (3, "reachability")):
        if all(item["status"] == "PASS" for item in stages):
            command = plan.fixture_preflight_commands[index]
            meaningful, binding = _fixture_stage_semantic(command, stage, workspace)
            if not meaningful:
                stages.append({"name": stage, "status": "FAIL", "reason": binding})
            else:
                results = run_acceptance_suite(workspace, (command,))
                status = results[0].status if len(results) == 1 else "FAIL"
                stages.append({
                    "name": stage,
                    "status": status,
                    "reason": results[0].reason if len(results) == 1 else "INCOMPLETE",
                    "semantic_binding": binding,
                })
    passed = len(stages) == 4 and all(item["status"] == "PASS" for item in stages)
    return q._control_receipt(
        "FIXTURE_PREFLIGHT_BEHAVIORAL",
        task_id=plan.task_id,
        execution_id=execution_id,
        head_sha=plan.base_head_sha,
        input_digest=sha256_json({"plan": plan.sha256, "stages": stages}),
        outcome="PASS" if passed else "FAIL",
        reason_code="FIXTURE_VALID" if passed else "FIXTURE_INVALID",
        evidence_refs=[f"fixture-v3:{item['name']}:{item['status']}" for item in stages],
        details={"stages": stages},
    )


def _persistence_applies(plan: q.QualityPlan) -> bool:
    return any(
        entry["dimension"] == "persistence" and entry["classification"] == "APPLIES"
        for entry in plan.risk_profile
    )


def run_readback_gate(
    manifest: ReadbackManifest,
    plan: q.QualityPlan,
    *,
    execution_id: str,
) -> dict[str, Any]:
    if manifest.task_id != plan.task_id:
        return q._control_receipt(
            "READBACK_FIELD_BINDING_TRUSTED",
            task_id=plan.task_id,
            execution_id=execution_id,
            head_sha=plan.base_head_sha,
            input_digest=manifest.sha256,
            outcome="FAIL",
            reason_code="READBACK_TASK_BINDING_MISMATCH",
        )
    persistence = _persistence_applies(plan)
    if not manifest.checks:
        return q._control_receipt(
            "READBACK_FIELD_BINDING_TRUSTED",
            task_id=plan.task_id,
            execution_id=execution_id,
            head_sha=plan.base_head_sha,
            input_digest=manifest.sha256,
            outcome="FAIL" if persistence else "N/A",
            reason_code="READBACK_REQUIRED_FOR_PERSISTENCE" if persistence else "READBACK_PROVEN_NOT_APPLICABLE",
            details={"persistence_applies": persistence, "justification": manifest.not_applicable_reason},
        )
    if persistence and any(check["source"]["kind"] != "supabase_rest" for check in manifest.checks):
        return q._control_receipt(
            "READBACK_FIELD_BINDING_TRUSTED",
            task_id=plan.task_id,
            execution_id=execution_id,
            head_sha=plan.base_head_sha,
            input_digest=manifest.sha256,
            outcome="FAIL",
            reason_code="READBACK_TRUSTED_SOURCE_REQUIRED",
            details={"allowed_persistence_sources": ["supabase_rest"]},
        )
    children: list[dict[str, Any]] = []
    refs: list[str] = []
    for index, check in enumerate(manifest.checks):
        try:
            row, digest = v2._observed_row(check)
            refs.append(f"readback-source:{check['source']['kind']}:{digest}")
            child = q.readback_field_binding(
                entity=check["entity"],
                expected_entity=check["expected_entity"],
                row=row,
                pk_field=check["pk_field"],
                expected_pk=check["expected_pk"],
                field=check["field"],
                expected_value=check["expected_value"],
                expected_type=v2._ALLOWED_TYPES[check["expected_type"]],
                status_field=check["status_field"],
                expected_status=check["expected_status"],
                task_id=plan.task_id,
                execution_id=f"{execution_id}:readback:{index}",
                head_sha=plan.base_head_sha,
            )
        except (OSError, UnicodeError, ValueError, urllib.error.URLError) as exc:
            child = q._control_receipt(
                "READBACK_OBSERVATION",
                task_id=plan.task_id,
                execution_id=f"{execution_id}:readback:{index}",
                head_sha=plan.base_head_sha,
                input_digest=manifest.sha256,
                outcome="BLOCKED",
                reason_code=f"READBACK_OBSERVATION_BLOCKED:{type(exc).__name__}",
                details={"source_kind": check["source"]["kind"]},
            )
        children.append(child)
    failures = [item for item in children if item["outcome"] != "PASS"]
    return q._control_receipt(
        "READBACK_FIELD_BINDING_TRUSTED",
        task_id=plan.task_id,
        execution_id=execution_id,
        head_sha=plan.base_head_sha,
        input_digest=manifest.sha256,
        outcome="FAIL" if failures else "PASS",
        reason_code="READBACK_SOURCE_OF_TRUTH_MISMATCH" if failures else "READBACK_SOURCE_OF_TRUTH_MATCH",
        evidence_refs=refs + [f"readback:{item['output_digest']}" for item in children],
        details={
            "check_count": len(children),
            "failed_count": len(failures),
            "persistence_applies": persistence,
        },
    )


def _outer_receipt(
    plan: q.QualityPlan,
    spec: WorkerTaskSpec,
    controls: list[dict[str, Any]],
    legacy: q.ProgrammingQualityWorkerResult | None,
    *,
    status: str,
    reason: str,
    patch: str,
) -> q.ProgrammingQualityWorkerResult:
    value: dict[str, Any] = {
        "schema_version": 4,
        "task_id": plan.task_id,
        "task_sha256": spec.sha256,
        "base_head_sha": plan.base_head_sha,
        "source_snapshot_sha256": spec.source_snapshot_sha256,
        "quality_plan_sha256": plan.sha256,
        "controls": [
            {
                "control_id": item["control_id"],
                "outcome": item["outcome"],
                "reason_code": item["reason_code"],
                "output_digest": item["output_digest"],
            }
            for item in controls
        ],
        "legacy_quality_receipt_sha256": None if legacy is None else legacy.receipt["receipt_sha256"],
        "status": status,
        "reason": reason,
        "patch_sha256": sha256_bytes(patch.encode("utf-8")) if patch else None,
        "patch_delivered": status == "PASS",
        "commit_allowed": False,
        "push_allowed": False,
        "merge_allowed": False,
        "production_allowed": False,
        "independent_audit_required": True,
    }
    value["receipt_sha256"] = sha256_json(value)
    return q.ProgrammingQualityWorkerResult(value, patch if status == "PASS" else "")


def run_programming_quality_worker_hardened(
    repo_path: Path,
    spec: WorkerTaskSpec,
    client: Any,
    oracle: HiddenOracle,
    plan: q.QualityPlan,
    readback_manifest: ReadbackManifest,
    *,
    work_parent: Path | None = None,
) -> q.ProgrammingQualityWorkerResult:
    execution = plan.task_id
    if plan.task_id != spec.task_id or plan.base_head_sha != spec.base_head_sha:
        return _outer_receipt(
            plan,
            spec,
            [],
            None,
            status="BLOCKED",
            reason="QUALITY_PLAN_TASK_BINDING_MISMATCH",
            patch="",
        )
    try:
        baseline = q.load_baseline(repo_path / "quality/programming_quality/baseline_v1.json")
    except ValueError as exc:
        return _outer_receipt(
            plan,
            spec,
            [],
            None,
            status="BLOCKED",
            reason=f"BASELINE_INVALID:{exc}",
            patch="",
        )
    controls = [
        v2.evaluate_bound_risk_profile(plan, spec, oracle, execution_id=execution),
        hidden_contract_receipt(plan, oracle, baseline, execution_id=execution),
        run_readback_gate(readback_manifest, plan, execution_id=execution),
    ]
    failed = next(
        (item for item in controls if item["outcome"] in {"FAIL", "BLOCKED"}),
        None,
    )
    if failed is not None:
        return _outer_receipt(
            plan,
            spec,
            controls,
            None,
            status="BLOCKED",
            reason=failed["reason_code"],
            patch="",
        )
    try:
        identity = verify_source_repository(repo_path, spec)
        parent = None if work_parent is None else str(work_parent)
        with tempfile.TemporaryDirectory(
            prefix="programming-agent-aud22-preflight-",
            dir=parent,
        ) as temporary:
            workspace = Path(temporary) / "fixture"
            create_disposable_workspace(repo_path, workspace, identity)
            fixture = run_canonical_fixture_preflight(
                workspace,
                plan,
                execution_id=execution,
            )
    except WorkspaceError as exc:
        fixture = q._control_receipt(
            "FIXTURE_PREFLIGHT_BEHAVIORAL",
            task_id=plan.task_id,
            execution_id=execution,
            head_sha=plan.base_head_sha,
            input_digest=plan.sha256,
            outcome="BLOCKED",
            reason_code=str(exc),
        )
    controls.append(fixture)
    if fixture["outcome"] != "PASS":
        return _outer_receipt(
            plan,
            spec,
            controls,
            None,
            status="BLOCKED",
            reason=fixture["reason_code"],
            patch="",
        )
    legacy = q.run_programming_quality_worker(
        repo_path,
        spec,
        client,
        oracle,
        plan,
        work_parent=work_parent,
        execution_id=execution,
    )
    if legacy.receipt["status"] != "PASS":
        return _outer_receipt(
            plan,
            spec,
            controls,
            legacy,
            status=legacy.receipt["status"],
            reason=legacy.receipt["reason"],
            patch="",
        )
    try:
        identity = verify_source_repository(repo_path, spec)
        parent = None if work_parent is None else str(work_parent)
        with tempfile.TemporaryDirectory(
            prefix="programming-agent-aud22-postgreen-",
            dir=parent,
        ) as temporary:
            candidate = Path(temporary) / "candidate"
            create_disposable_workspace(repo_path, candidate, identity)
            replay_cumulative_patch(candidate, legacy.patch)
            semantic = conservative_semantic_gate(
                candidate,
                plan,
                execution_id=execution,
            )
    except WorkspaceError as exc:
        semantic = q._control_receipt(
            "SEMANTIC_BEHAVIORAL_GUARD",
            task_id=plan.task_id,
            execution_id=execution,
            head_sha=plan.base_head_sha,
            input_digest=plan.sha256,
            outcome="BLOCKED",
            reason_code=str(exc),
        )
    controls.append(semantic)
    if semantic["outcome"] in {"FAIL", "BLOCKED"}:
        return _outer_receipt(
            plan,
            spec,
            controls,
            legacy,
            status=semantic["outcome"],
            reason=semantic["reason_code"],
            patch="",
        )
    return _outer_receipt(
        plan,
        spec,
        controls,
        legacy,
        status="PASS",
        reason="AUD22_HARDENED_PROGRAMMING_QUALITY_GATE_PASSED",
        patch=legacy.patch,
    )
