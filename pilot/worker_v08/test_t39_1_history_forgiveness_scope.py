"""T39.1: forgiveness records must not shadow the current run id in admit_attempt.

Regression: a forgiven earlier run made a later, legitimate prior proof look
newer than the current run (NATIVE_PRIOR_PROOF_MISMATCH)."""
import ast
from pathlib import Path
import json

import native_run_history as h

PACK = "c" * 64
SRC = Path(h.__file__)


def test_admit_attempt_never_rebinds_run_id():
    tree = ast.parse(SRC.read_text("utf-8"))
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "admit_attempt")
    for node in ast.walk(fn):
        targets = []
        if isinstance(node, (ast.For, ast.comprehension)):
            targets = [node.target]
        elif isinstance(node, ast.Assign):
            targets = node.targets
        for t in targets:
            names = {n.id for n in ast.walk(t) if isinstance(n, ast.Name)}
            assert "run_id" not in names, "admit_attempt rebinds run_id"


def _run(i, sha):
    return {"id": i, "status": "completed", "conclusion": "failure", "head_branch": "main",
            "run_attempt": 1, "event": "workflow_run",
            "display_title": f"lf-native-auto-lf/native-proposal/req9backend2-{sha}"}


def test_prior_proof_after_forgiven_run_is_counted(tmp_path, monkeypatch):
    runs = [_run(50, "e" * 40), _run(40, "d" * 40), _run(30, "b" * 40), _run(20, "a" * 40)]
    proofs = {20: 1, 30: 2, 40: 2}  # 30 forgiven; 40 retook attempt 2
    monkeypatch.setattr(h, "_api", lambda b, t, r: {"total_count": len(runs), "workflow_runs": runs})
    monkeypatch.setattr(h, "_artifact_json", lambda b, t, rid: None if rid not in proofs else
                        {"task_id": "req9backend2", "attempt": proofs[rid], "task_pack_sha256": PACK, "run_id": rid})
    import native_intake_defect as d
    monkeypatch.setattr(d, "verified_intake_defects",
                        lambda c, t, r: {30: {"proposal_commit_sha": "b" * 40, "task_pack_sha256": PACK}})
    out = tmp_path / "h.json"
    got = h.admit_attempt(repository="paulozterra/lf-programming-sandbox", token="x", task="req9backend2",
                          attempt=None, run_id=50, run_attempt=1, sha="e" * 40, output=out,
                          event="workflow_run", proposal_branch="lf/native-proposal/req9backend2")
    assert got == 3 and json.loads(out.read_text())["route_defect_run_ids"] == [30]
