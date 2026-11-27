#!/usr/bin/env python3
"""A4: assemble an audit_report_v2 from an auditor draft (route adapter).

The auditor writes only judgement in `draft.json` (LF_ROUTE_AUDIT_DRAFT_V1):
rule tasks, findings, evidence list, EKB checklist and limitations. This tool
fills every mechanical field from the repository so it cannot drift:
sha256 of each capture and finding file, the literal found_code from the
line range at base_commit, collected_at, and — for route requests, which are
not runs of the LF 11-step agent pipeline — the step/hop ledger marked as not
executed. Completion (coverage and flow verdict) is computed with the pinned
skill's own functions. The skill validator stays the judge.

Usage:
  report_scaffold.py --skill-dir <skill> --audit-dir pilot/runs/<req>/audit
Reads <audit-dir>/audit_input_v2.json and <audit-dir>/draft.json, writes
<audit-dir>/report.json.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DRAFT_SCHEMA = "LF_ROUTE_AUDIT_DRAFT_V1"
SCOPES = {"LOCAL_REAL_LF_HELPER", "FIXTURE_ONLY", "STATIC_SQL_READBACK", "NOT_EXECUTED"}


class ScaffoldError(ValueError):
    pass


def _sha(root: Path, ref: str) -> str:
    path = (root / ref.partition("#")[0]).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ScaffoldError("SCAFFOLD_CAPTURE_MISSING:" + ref)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _at_commit(root: Path, commit: str, file: str) -> bytes:
    try:
        return subprocess.run(["git", "-C", str(root), "show", f"{commit}:{file}"],
                              capture_output=True, check=True).stdout
    except subprocess.CalledProcessError:
        raise ScaffoldError("SCAFFOLD_FILE_NOT_AT_COMMIT:" + file) from None


def assemble(draft: dict, audit_input: dict, skill_dir: Path, root: Path = ROOT, now: str | None = None) -> dict:
    if draft.get("schema_version") != DRAFT_SCHEMA:
        raise ScaffoldError("SCAFFOLD_DRAFT_SCHEMA")
    sys.path.insert(0, str(skill_dir / "scripts"))
    from audit_v2 import STEP_ORDERS, flow_verdict, lot_coverage, sample_metrics
    now = now or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    base = audit_input["base_commit"]
    criteria = dict(c.split(" :: ", 1) for c in audit_input["acceptance_criteria"])

    # A new audit must actually inspect its declared revision. Do not silently
    # hash current code as historical evidence, or backdate a new capture.
    audit_dir = audit_input.get("evidence_destination", "")
    def capture_sha(ref):
        name = ref.partition("#")[0]
        digest = _sha(root, ref)
        if not audit_dir or not name.startswith(audit_dir + "/"):
            if hashlib.sha256(_at_commit(root, base, name)).hexdigest() != digest:
                raise ScaffoldError("SCAFFOLD_FILE_CHANGED_SINCE_CLOSE:" + name)
        return digest

    evidence = [{"id": e["id"], "kind": e["kind"], "origin": e["origin"], "capture_ref": e["ref"],
                 "source_execution_id": None, "observed_at": e.get("observed_at"), "collected_at": now,
                 "claim": e["claim"], "capture_sha256": capture_sha(e["ref"])} for e in draft["evidence"]]
    kinds = {e["id"]: e["kind"] for e in evidence}

    missing = sorted(set(criteria) - set(draft["tasks"]))
    if missing:
        raise ScaffoldError("SCAFFOLD_TASK_MISSING:" + missing[0])
    tasks = [{"id": code, "description": criteria.get(code, t.get("description", "")), "status": t["status"],
              "evidence_refs": t["evidence_refs"], "reason": t["reason"]}
             for code, t in draft["tasks"].items()]

    findings = []
    for f in draft["findings"]:
        data = _at_commit(root, base, f["file"])
        local = (root / f["file"]).read_bytes()
        if local != data:
            # A9: same content, CRLF on disk = a checkout with core.autocrlf (Windows).
            if local.replace(b"\r\n", b"\n") == data and b"\r\n" not in data:
                raise ScaffoldError("SCAFFOLD_CHECKOUT_EOL_CONVERTED:" + f["file"])
            raise ScaffoldError("SCAFFOLD_FILE_CHANGED_SINCE_CLOSE:" + f["file"])
        lines = data.decode().splitlines()
        executed = bool(f.get("command"))
        scope = f.get("scope", "LOCAL_REAL_LF_HELPER" if executed else "NOT_EXECUTED")
        if scope not in SCOPES:
            raise ScaffoldError("SCAFFOLD_SCOPE:" + f["id"])
        run = [f["run_file"]] if f.get("run_file") else []
        refs = f["evidence_refs"]
        findings.append({
            "id": f["id"], "kind": f["kind"], "code": f["code"],
            "location": {"file": f["file"], "function": f["function"], "start_line": f["start_line"],
                         "end_line": f["end_line"], "commit": base, "sha256": hashlib.sha256(data).hexdigest()},
            "found_code": "\n".join(lines[f["start_line"] - 1:f["end_line"]]),
            "expected": {"behavior": f["behavior"], "contract_refs": f["contract_refs"]},
            "defect": f["defect"], "root_cause": f["root_cause"], "impact": f["impact"],
            "correction": {"code": f["correction"], "targets": f["targets"], "proposed_only": True},
            "positive_test": {"description": f["positive"]["description"], "evidence_ref": f["positive"].get("ref"),
                              "executed": bool(f["positive"].get("ref"))},
            "negative_test": {"description": f["negative"]["description"], "evidence_ref": f["negative"].get("ref"),
                              "executed": bool(f["negative"].get("ref"))},
            "observed_result": {"executed": executed, "command": f.get("command"), "exit_code": 0 if executed else None,
                                "summary": f.get("summary", "Ver salida del reproductor." if executed else "No ejecutado."),
                                "evidence_refs": run, "scope": scope},
            "readback": {"verified": executed, "consumer": f.get("consumer", ""), "effect": f.get("effect", "ninguno (solo lectura)"),
                         "evidence_refs": run},
            "status": f.get("status", "CONFIRMED" if executed else "HYPOTHESIS"),
            "before_ref": None, "after_ref": None, "fix_scope": "NONE",
            "evidence_kind": "MEASURED_THIS_AUDIT" if any(kinds.get(r) == "MEASURED_THIS_AUDIT" for r in refs)
            else "CODE_READ_ONLY",
            "confidence": f["confidence"], "confidence_reason": f["confidence_reason"],
            "current_audit_evidence_refs": refs})

    # Route requests are not runs of the LF agent pipeline: the 11-step ledger
    # is recorded as not executed, with the reason, never as accredited.
    reason = draft.get("pipeline_reason", "El pedido de la ruta no se ejecuta por el pipeline LF de 11 pasos; se audita el código integrado.")
    steps = [{"order": o, "name": f"Paso LF {o}", "execution_id": None, "reported_status": "NOT_APPLICABLE_ROUTE_REQUEST",
              "what_worked": reason, "behavior_status": "NOT_EXECUTED", "runtime_origin": "NONE",
              "evidence_kind": "NOT_MEASURED", "evidence_refs": [], "resolved_receipts": [],
              "unresolved": ["Sin corrida LF para este pedido."], "confidence": "HIGH",
              "confidence_reason": "La ruta no ejecuta los pasos LF.", "receipt_ref": None} for o in STEP_ORDERS]
    hops = [{"id": f"HOP-{a}-{b}", "from_step": a, "to_step": b, "sender": f"paso {a}", "receiver": f"paso {b}",
             "fields_sent": [], "fields_lost": [], "run_binding": "NOT_APPLICABLE", "hash_binding": "NOT_APPLICABLE",
             "hash_semantics": "No aplica.", "applicability_reason": reason, "evidence_refs": [], "unverified": []}
            for a, b in zip(STEP_ORDERS, STEP_ORDERS[1:])]
    cohort = draft["cohort_ref"]
    evidence.append({"id": "EV-COHORT", "kind": "NOT_MEASURED", "origin": "NONE", "capture_ref": cohort,
                     "source_execution_id": None, "observed_at": None, "collected_at": now,
                     "claim": "Sin corridas del pipeline LF para este pedido: cohorte vacía.",
                     "capture_sha256": capture_sha(cohort)})
    report = {
        "schema_version": "LF_DEEP_AUDIT_REPORT_V2", "phases": [1, 2, 3, 4, 5, 6],
        "checklist": draft["checklist"],
        "audit_context": {"audit_id": f"AUDIT-{audit_input.get('evidence_destination', '').split('/')[-2]}-{now[:10]}",
                          "source_revision": base, "started_at": now, "source_execution_id": None,
                          "source_run_started_at": None, "new_e2e_executed": False, "ig_execution_required": False,
                          "ig_invocation_verified": False, "promotion_authorized": False, "authority_ref": None},
        "audit_tasks": tasks, "evidence_catalog": evidence, "steps": steps, "hops": hops,
        "sql_queries": draft.get("sql_queries", []), "pass_emitters": [],
        "pass_scan_scope": {"files": draft.get("scanned_files", []), "literal_scan_complete": False,
                            "dynamic_emissions_complete": False,
                            "limitations": ["Inventario de emisores PASS no aplica al código de producto."]},
        "run_sample": {"query": "corridas LF del pedido", "requested_n": 1, "sampled_runs": 0,
                       "metrics": sample_metrics([]), "evidence_refs": ["EV-COHORT"],
                       "limitations": ["El pedido no tiene corridas del pipeline LF."]},
        "contracts": [], "findings": findings, "limitations": draft["limitations"],
    }
    report["completion"] = {"lot_coverage_percent": lot_coverage(tasks)["percent"], "flow_verdict": "FLOW_NOT_ACCREDITED",
                            "flow_reasons": [], "unknown_scope": draft.get("unknown_scope", [])}
    verdict = flow_verdict(report)
    report["completion"]["flow_verdict"], report["completion"]["flow_reasons"] = verdict["verdict"], verdict["reasons"]
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skill-dir", type=Path, required=True)
    ap.add_argument("--audit-dir", type=Path, required=True)
    a = ap.parse_args()
    try:
        draft = json.loads((a.audit_dir / "draft.json").read_text("utf-8"))
        audit_input = json.loads((a.audit_dir / "audit_input_v2.json").read_text("utf-8"))
        report = assemble(draft, audit_input, a.skill_dir)
    except (ScaffoldError, OSError, ValueError, KeyError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}))
        return 1
    (a.audit_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps({"status": "REPORT_ASSEMBLED", "tasks": len(report["audit_tasks"]),
                      "findings": len(report["findings"]), "flow_verdict": report["completion"]["flow_verdict"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
