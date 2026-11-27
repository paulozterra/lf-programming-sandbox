#!/usr/bin/env python3
"""T46: build the audit input (LF_DEEP_AUDIT_INPUT_V2) for a closed request.

Derived only from route artifacts and git history, never typed by hand:
* the request is closed when every lot of its chain plan has an attested
  verified-integration merge (the same proof CP3.6 uses, chain_lots.completed_lots);
* base_commit is the latest of those merges;
* read_scope/entrypoints are the files the lots actually integrated (T43);
* acceptance_criteria are the request's requirements, one per rule, as
  "RULE:<code> :: <outcome>" so the report must account for each (T46 route
  check AUDIT_CRITERIA_UNCOVERED).
"""
from __future__ import annotations
# Direct-script entrypoint: resolve the trusted repository root from this file,
# not from the caller's working directory or PYTHONPATH.
import sys as _project_sys
from pathlib import Path as _project_Path
_project_sys.path.insert(0, str(_project_Path(__file__).resolve().parents[2]))
from pilot.config.project_config import storage_path, storage

import argparse
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pilot/orchestrator"))
sys.path.insert(0, str(ROOT / "pilot/worker_v08"))
from audit_config import AuditConfigError, load  # noqa: E402

SCHEMA = "LF_DEEP_AUDIT_INPUT_V2"
NOT_CODE = ("standards/", "pilot/")


class AuditInputError(ValueError):
    pass


def rule_criteria(analysis: dict) -> list[str]:
    rows = []
    for req in analysis.get("requirements", []):
        if not isinstance(req, dict):
            continue
        code = req.get("source_requirement_id") or req.get("requirement_id")
        outcome = req.get("outcome") or req.get("acceptance_signal") or ""
        if isinstance(code, str) and code:
            rows.append(f"RULE:{code} :: {outcome}".strip())
    if not rows:
        raise AuditInputError("AUDIT_INPUT_NO_RULES")
    return sorted(set(rows))


def closing_merge(shas: list[str], root: Path = ROOT) -> str:
    """The merge that has every other lot merge as ancestor closes the request."""
    import subprocess
    unique = sorted(set(shas))
    for cand in unique:
        if all(other == cand or subprocess.run(
                ["git", "-C", str(root), "merge-base", "--is-ancestor", other, cand],
                capture_output=True).returncode == 0 for other in unique):
            return cand
    raise AuditInputError("AUDIT_INPUT_MERGES_NOT_LINEAR")


def build(request: str, project: str, repository: str, completed: dict, lots: dict,
          analysis: dict, root: Path = ROOT) -> dict:
    """completed: {lot_id: receipt} where receipt has merge_sha and expected_files."""
    config = load(project, root)
    by_id = {lot["id"]: lot for lot in lots["lots"]}
    if not completed or set(completed) != set(by_id):
        raise AuditInputError("AUDIT_REQUEST_NOT_CLOSED")
    shas = [r.get("merge_sha") for r in completed.values()]
    if not all(isinstance(s, str) and len(s) == 40 for s in shas):
        raise AuditInputError("AUDIT_INPUT_RECEIPT_INVALID")
    base = closing_merge(shas, root)
    files = sorted({f for r in completed.values() for f in r.get("expected_files", [])
                    if not f.startswith(NOT_CODE)})
    if not files:
        raise AuditInputError("AUDIT_INPUT_NO_INTEGRATED_FILES")
    run_dir = f"pilot/runs/{request}"
    from historical_evidence import tree_blob, EvidenceError
    refs = []
    historical = {}
    for rel in (f"{run_dir}/analysis.json", f"{run_dir}/lots.json"):
        try:
            data = tree_blob(root, base, rel)
            historical[rel] = json.loads(data)
        except (EvidenceError, ValueError, TypeError) as exc:
            raise AuditInputError("AUDIT_INPUT_HISTORICAL_AUTHORITY_UNRESOLVED") from exc
        refs.append({"uri": f"github://{repository}@{base}/{rel}",
                     "expected_sha256": hashlib.sha256(data).hexdigest(),
                     "resolved_revision": base, "resolution_status": "DECLARED_ONLY"})
    # The producer and consumer must agree with the closing revision; refuse
    # a changed analysis or lot plan instead of creating contradictory input.
    if historical[f"{run_dir}/analysis.json"] != analysis or historical[f"{run_dir}/lots.json"] != lots:
        raise AuditInputError("AUDIT_INPUT_HISTORICAL_AUTHORITY_DRIFT")
    consumers = sorted({f for lot in lots["lots"] if lot["depends_on"]
                        for f in completed[lot["id"]].get("expected_files", [])
                        if not f.startswith(NOT_CODE)}) or files
    audit = config["audit"]
    return {
        "schema_version": SCHEMA,
        "repository": repository,
        "base_commit": base,
        "objective": (f"Auditar la implementación integrada del pedido {request} contra su ficha "
                      f"(reglas) y sus contratos, leyendo el código real en {base[:12]}."),
        "read_scope": files + [f"{run_dir}/analysis.json", f"{run_dir}/lots.json"],
        "write_scope": ["TEST_LOCAL", "UPDATE_DRAFT_PR"],
        "entrypoints": files,
        "consumer_targets": consumers,
        "authority_refs": refs,
        "acceptance_criteria": rule_criteria(analysis),
        "evidence_destination": f"{run_dir}/audit",
        "new_e2e_requested": False,
        "ig_execution_required": False,
        "sample_n": audit["sample_n"],
        "performance_budget_ms": audit["performance_budget_ms"],
        "freshness_budget_ms": audit["freshness_budget_ms"],
    }


def completed_from_history(request: str) -> tuple[dict, dict]:
    """Same attestation CP3.6 uses; requires git history and the GitHub API."""
    import chain_lots as cl
    for req, lots, _state, bindings in cl.plans():
        if req == request:
            done = cl.completed_lots(lots, bindings, cl.first_parent_merges(req))
            return lots, {lot_id: dict(r)
                          for lot_id, r in done.items()}
    raise AuditInputError("AUDIT_REQUEST_UNKNOWN")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--request", required=True)
    ap.add_argument("--repository", required=True)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    try:
        lots, done = completed_from_history(a.request)
        analysis = json.loads((storage_path("requests_root", root=ROOT) / a.request / "analysis.json").read_text("utf-8"))
        data = build(a.request, a.project, a.repository, done, lots, analysis)
    except (AuditConfigError, AuditInputError, OSError, ValueError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}))
        return 1
    text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(text, "utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
