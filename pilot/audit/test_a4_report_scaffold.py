"""A4: the route adapter rebuilds a valid audit_report_v2 from an auditor draft."""
import json
import os
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import report_scaffold as rs  # noqa: E402

ROOT = HERE.parents[1]
AUDIT = ROOT / "pilot/runs/req-286/audit"


def draft_from(report: dict) -> dict:
    """Invert a merged report into the auditor's judgement-only draft."""
    ev = [{"id": e["id"], "ref": e["capture_ref"], "kind": e["kind"], "origin": e["origin"], "claim": e["claim"]}
          for e in report["evidence_catalog"] if e["id"] != "EV-COHORT"]
    cohort = next(e["capture_ref"] for e in report["evidence_catalog"] if e["id"] == "EV-COHORT")
    findings = []
    for f in report["findings"]:
        loc = f["location"]
        findings.append({
            "id": f["id"], "kind": f["kind"], "code": f["code"], "file": loc["file"], "function": loc["function"],
            "start_line": loc["start_line"], "end_line": loc["end_line"], "behavior": f["expected"]["behavior"],
            "contract_refs": f["expected"]["contract_refs"], "defect": f["defect"], "root_cause": f["root_cause"],
            "impact": f["impact"], "correction": f["correction"]["code"], "targets": f["correction"]["targets"],
            "positive": {"description": f["positive_test"]["description"], "ref": f["positive_test"]["evidence_ref"]},
            "negative": {"description": f["negative_test"]["description"], "ref": f["negative_test"]["evidence_ref"]},
            "command": f["observed_result"]["command"], "run_file": f["observed_result"]["evidence_refs"][0],
            "consumer": f["readback"]["consumer"], "effect": f["readback"]["effect"],
            "summary": f["observed_result"]["summary"], "evidence_refs": f["current_audit_evidence_refs"],
            "confidence": f["confidence"], "confidence_reason": f["confidence_reason"]})
    return {"schema_version": rs.DRAFT_SCHEMA, "evidence": ev, "cohort_ref": cohort,
            "tasks": {t["id"]: {"status": t["status"], "evidence_refs": t["evidence_refs"], "reason": t["reason"]}
                      for t in report["audit_tasks"]},
            "findings": findings, "checklist": report["checklist"], "limitations": report["limitations"],
            "unknown_scope": report["completion"]["unknown_scope"]}


def skill_dir():
    d = os.environ.get("LF_AUDIT_SKILL_DIR")
    if not d:
        pytest.skip("skill not fetched")
    return Path(d)


def test_rebuilds_req286_report_identically_in_judgement():
    skill = skill_dir()
    report = json.loads((AUDIT / "report.json").read_text())
    audit_input = json.loads((AUDIT / "audit_input_v2.json").read_text())
    from historical_evidence import evidence_view
    with evidence_view(ROOT, AUDIT / "report.json", report, audit_input) as view:
        rebuilt = rs.assemble(draft_from(report), audit_input, skill, root=view,
                              now=report["audit_context"]["started_at"])
    for key in ("audit_tasks", "findings", "checklist", "completion"):
        assert rebuilt[key] == report[key], key
    # The 11-step ledger carries standard boilerplate; only its structure must match.
    strip = lambda rows, keys: [{k: v for k, v in r.items() if k not in keys} for r in rows]
    text = {"what_worked", "reported_status", "confidence_reason", "applicability_reason"}
    assert strip(rebuilt["steps"], text) == strip(report["steps"], text)
    assert strip(rebuilt["hops"], text) == strip(report["hops"], text)


def test_rebuilt_report_passes_the_skill_validator():
    skill = skill_dir()
    pytest.importorskip("jsonschema")
    sys.path.insert(0, str(skill / "validators"))
    from validate_audit_v2 import validate
    report = json.loads((AUDIT / "report.json").read_text())
    from historical_evidence import evidence_view
    audit_input = json.loads((AUDIT / "audit_input_v2.json").read_text())
    with evidence_view(ROOT, AUDIT / "report.json", report, audit_input) as view:
        rebuilt = rs.assemble(draft_from(report), audit_input, skill, root=view)
        assert validate(rebuilt, view) == []
    from pilot.audit.validate_report import validate as validate_route
    assert validate_route(AUDIT / "report.json", skill, ROOT) == []


def test_missing_rule_task_blocks():
    skill = skill_dir()
    report = json.loads((AUDIT / "report.json").read_text())
    draft = draft_from(report)
    draft["tasks"].pop(next(iter(draft["tasks"])))
    from historical_evidence import evidence_view
    audit_input = json.loads((AUDIT / "audit_input_v2.json").read_text())
    with evidence_view(ROOT, AUDIT / "report.json", report, audit_input) as view:
        with pytest.raises(rs.ScaffoldError, match="SCAFFOLD_TASK_MISSING"):
            rs.assemble(draft, audit_input, skill, root=view)


def test_wrong_draft_schema_blocks(tmp_path):
    with pytest.raises(rs.ScaffoldError, match="SCAFFOLD_DRAFT_SCHEMA"):
        rs.assemble({"schema_version": "X"}, {}, tmp_path)


def test_crlf_checkout_is_named_not_reported_as_drift(tmp_path):
    import subprocess
    r = tmp_path / "repo"
    r.mkdir()
    (r / "a.txt").write_bytes(b"uno\ndos\n")
    for c in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x"]):
        subprocess.run(["git", "-C", str(r), *c], check=True, capture_output=True)
    sha = subprocess.run(["git", "-C", str(r), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    (r / "a.txt").write_bytes(b"uno\r\ndos\r\n")
    draft = {"schema_version": rs.DRAFT_SCHEMA, "evidence": [], "tasks": {},
             "findings": [{"id": "F", "file": "a.txt", "start_line": 1, "end_line": 1}]}
    skill = tmp_path / "skill/scripts"
    skill.mkdir(parents=True)
    (skill / "audit_v2.py").write_text("STEP_ORDERS=[]\ndef flow_verdict(r): pass\ndef lot_coverage(t): pass\n"
                                       "def sample_metrics(r): pass\n")
    sys.modules.pop("audit_v2", None)
    with pytest.raises(rs.ScaffoldError, match="SCAFFOLD_CHECKOUT_EOL_CONVERTED:a.txt"):
        rs.assemble(draft, {"base_commit": sha, "acceptance_criteria": []}, skill.parent, root=r)
    sys.modules.pop("audit_v2", None)
