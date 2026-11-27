#!/usr/bin/env python3
"""T46: validate an audit report published by the route's audit stage.

Two layers, both deterministic:
1. the skill's own validator (validate_audit_v2.validate), taken from the
   pinned and hash-verified skill (skill_pin), against this repository;
2. route checks on top of the V2 format:
   * the report was produced from the route's input (audit_input_v2.json next to it);
   * audit_context.source_revision == input.base_commit (the request's closing merge);
   * promotion_authorized is false (the stage never authorizes effects);
   * one audit task "RULE:<code>" per acceptance criterion (inverse trace, H4);
   * every EKB code cited in the checklist exists in the live EKB (codes only).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
from audit_config import AuditConfigError, load  # noqa: E402
from historical_evidence import evidence_view, EvidenceError  # noqa: E402


def route_checks(report: dict, audit_input: dict, ekb_codes: list[str] | None) -> list[str]:
    errors = []
    ctx = report.get("audit_context") or {}
    if ctx.get("source_revision") != audit_input.get("base_commit"):
        errors.append("AUDIT_REPORT_INVALID:SOURCE_REVISION_NOT_REQUEST_CLOSE")
    if ctx.get("promotion_authorized") is not False:
        errors.append("AUDIT_REPORT_INVALID:PROMOTION_NOT_ALLOWED")
    tasks = {t.get("id"): t for t in report.get("audit_tasks", []) if isinstance(t, dict)}
    for criterion in audit_input.get("acceptance_criteria", []):
        code = criterion.split(" :: ", 1)[0]
        task = tasks.get(code)
        if task is None:
            errors.append("AUDIT_CRITERIA_UNCOVERED:" + code)
        elif task.get("status") in ("NOT_APPLICABLE", "NOT_EXECUTED", "BLOCKED") \
                and not (task.get("reason") or "").strip():
            errors.append("AUDIT_CRITERIA_UNJUSTIFIED:" + code)
    if ekb_codes is not None:
        known = set(ekb_codes)
        for check in report.get("checklist", []):
            if isinstance(check, dict) and check.get("ekb_code") not in known:
                errors.append("AUDIT_EKB_CODE_UNKNOWN:" + str(check.get("ekb_code")))
    return errors


def skill_checks(report: dict, skill_dir: Path, root: Path) -> list[str]:
    sys.path.insert(0, str(skill_dir / "scripts"))
    sys.path.insert(0, str(skill_dir / "validators"))
    try:
        from validate_audit_v2 import validate
    except ImportError as exc:
        return ["AUDIT_SKILL_VALIDATOR_UNAVAILABLE:" + type(exc).__name__]
    return ["SKILL:" + e for e in validate(report, root)]


def validate(report_file: Path, skill_dir: Path, root: Path = ROOT,
             ekb_codes: list[str] | None = None) -> list[str]:
    try:
        report = json.loads(report_file.read_text("utf-8"))
        audit_input = json.loads((report_file.parent / "audit_input_v2.json").read_text("utf-8"))
    except (OSError, ValueError):
        return ["AUDIT_REPORT_INVALID:UNREADABLE"]
    if not isinstance(report, dict) or not isinstance(audit_input, dict):
        return ["AUDIT_REPORT_INVALID:NOT_OBJECT"]
    errors = route_checks(report, audit_input, ekb_codes)
    try:
        with evidence_view(root, report_file, report, audit_input) as view:
            return errors + skill_checks(report, skill_dir, view)
    except EvidenceError as exc:
        return errors + [str(exc)]
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return errors + ["AUDIT_PROVENANCE:UNRESOLVED"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--skill-dir", type=Path, required=True)
    ap.add_argument("--report", type=Path, action="append", default=[])
    ap.add_argument("--all", action="store_true", help="every pilot/runs/*/audit/report.json")
    ap.add_argument("--ekb", action="store_true", help="check EKB codes live (needs the secret)")
    a = ap.parse_args()
    try:
        config = load(a.project)
    except AuditConfigError as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}))
        return 1
    reports = list(a.report) + (sorted(ROOT.glob("pilot/runs/*/audit/report.json")) if a.all else [])
    codes = None
    if a.ekb:
        from ekb_reader import EkbError, read_codes
        try:
            codes = read_codes(config)
        except EkbError as exc:
            print(json.dumps({"status": "BLOCKED", "reason": str(exc)}))
            return 1
    failed = False
    for file in reports:
        errors = validate(file, a.skill_dir, ROOT, codes)
        print(json.dumps({"report": str(file.relative_to(ROOT)) if file.is_absolute() else str(file),
                          "status": "AUDIT_REPORT_VALID" if not errors else "AUDIT_REPORT_INVALID",
                          "errors": errors[:50], "error_count": len(errors)}))
        failed |= bool(errors)
    if not reports:
        print(json.dumps({"status": "NO_AUDIT_REPORTS"}))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
