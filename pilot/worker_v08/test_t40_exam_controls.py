"""T40: exam controls (rehearsal before use, positive control at run time,
traceable failure codes)."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pilot/orchestrator"))

import native_exam_control as c  # noqa: E402
import native_run  # noqa: E402
from native_feedback_delivery import parse_feedback  # noqa: E402
from holdout_age import decrypt_reference  # noqa: E402
import publish_exam as pe  # noqa: E402

SHA = "a" * 64


def _env_block(text: str, start: str, end: str) -> str:
    i = text.index(start)
    return text[i:text.index(end, i)]


def test_rehearsal_environment_is_the_worker_environment():
    worker = (ROOT / ".github/workflows/worker-native.yml").read_text("utf-8")
    rehearsal = (ROOT / ".github/workflows/exam-rehearsal.yml").read_text("utf-8")
    env = _env_block(worker, "      - name: Set up Python\n", "      - name: Check vendored source integrity")
    assert env in rehearsal
    services = _env_block(worker, "    services:\n", "    steps:\n")
    assert services in rehearsal
    age = _env_block(worker, "      - name: Install age v1.3.2", "      - name: Decode task-selected")
    assert age.replace("        if: ${{ steps.task.outputs.holdout_ref != '' }}\n", "") in rehearsal


def test_reference_is_bound_to_one_exam_version():
    raw = json.dumps({"schema_version": c.SCHEMA, "task": "req9backend2",
                      "holdout_sha256": SHA, "patch": "--- a/x\n+++ b/x\n"}).encode()
    assert c.parse_reference(raw, "req9backend2", SHA)
    with pytest.raises(ValueError, match="EXAM_REFERENCE_FOR_OTHER_EXAM"):
        c.parse_reference(raw, "req9backend2", "b" * 64)
    with pytest.raises(ValueError):
        c.parse_reference(raw, "req9other", SHA)


def test_changed_paths_from_patch():
    patch = ("diff --git a/n.txt b/n.txt\nnew file mode 100644\n--- /dev/null\n+++ b/n.txt\n@@ -0,0 +1 @@\n+x\n"
             "diff --git a/o.txt b/o.txt\ndeleted file mode 100644\n--- a/o.txt\n+++ /dev/null\n@@ -1 +0,0 @@\n-y\n")
    assert c.changed_paths(patch) == ["n.txt", "o.txt"]


def test_examiner_defect_line_is_publishable_feedback():
    fb = native_run._visible_feedback(None, 2)
    fb["commands"].append(c.feedback_line())
    parse_feedback(json.dumps(fb).encode(), 2)  # no private pattern, valid schema


def _public(tmp_path):
    public = tmp_path / "public"
    public.mkdir()
    for name in ("attempt-proof.json", "feedback.json", "status.json"):
        (public / name).write_text("{}")
    return public


SUBMITTED = {"proposal_sha256": "c" * 64, "task_pack_sha256": "d" * 64}


def test_reference_also_fails_means_not_charged(tmp_path, monkeypatch):
    public = _public(tmp_path)
    monkeypatch.setattr(c, "load_reference", lambda p, t, s: "patch")
    monkeypatch.setattr(c, "run_reference", lambda *a, **k: {"status": "FAIL", "reason": "HIDDEN_ORACLE_FAILED"})
    assert native_run._examiner_control(tmp_path, None, None, tmp_path, public, "req9backend2",
                                        7, SHA, 2, None, SUBMITTED) is True
    assert not (public / "attempt-proof.json").exists()
    fb = json.loads((public / "feedback.json").read_text())
    assert fb["commands"][-1]["reason"] == c.VERDICT_DEFECT
    assert json.loads((public / "status.json").read_text())["status"] == "BLOCKED"
    rec = json.loads((public / "examiner-control.json").read_text())
    assert rec["run_id"] == 7 and rec["verdict"] == c.VERDICT_DEFECT


def test_reference_passes_means_real_failure_is_charged(tmp_path, monkeypatch):
    public = _public(tmp_path)
    monkeypatch.setattr(c, "load_reference", lambda p, t, s: "patch")
    monkeypatch.setattr(c, "run_reference", lambda *a, **k: {"status": "PASS", "reason": "x"})
    assert native_run._examiner_control(tmp_path, None, None, tmp_path, public, "req9backend2",
                                        7, SHA, 2, None, SUBMITTED) is False
    assert (public / "attempt-proof.json").exists()


def test_no_reference_keeps_legacy_behaviour(tmp_path, monkeypatch):
    public = _public(tmp_path)
    monkeypatch.setattr(c, "load_reference", lambda p, t, s: None)
    assert native_run._examiner_control(tmp_path, None, None, tmp_path, public, "req9backend2",
                                        7, SHA, 2, None, SUBMITTED) is False
    assert (public / "attempt-proof.json").exists()


def test_missing_reference_cipher_is_optional(tmp_path):
    (tmp_path / "pilot/holdouts").mkdir(parents=True)
    assert decrypt_reference(tmp_path, "req9backend2", "AGE-SECRET-KEY-1X", tmp_path / "p") is None


def test_trace_must_cover_every_failure_code(tmp_path):
    script = 'fail("BUILD")\nfail("EMAIL_LOGIN")\nfail(f"MESSAGE_{x}")\n'
    (tmp_path / "contracts").mkdir()
    (tmp_path / "contracts/c.yaml").write_text("x")
    ok = {"BUILD": "env:compila el servicio", "EMAIL_LOGIN": "contract:contracts/c.yaml",
          "MESSAGE_": "request:req-9 decisión de mensajes"}
    pe.check_trace(script, ok, tmp_path, tmp_path, "req-9")
    with pytest.raises(pe.ExamBlocked, match="EXAM_TRACE_MISMATCH:missing=EMAIL_LOGIN"):
        pe.check_trace(script, {k: v for k, v in ok.items() if k != "EMAIL_LOGIN"},
                       tmp_path, tmp_path, "req-9")
    with pytest.raises(pe.ExamBlocked, match="EXAM_TRACE_RULE_UNKNOWN"):
        pe.check_trace(script, dict(ok, BUILD="rule:STD-NO-EXISTE-999"), tmp_path, tmp_path, "req-9")
    with pytest.raises(pe.ExamBlocked, match="EXAM_TRACE_KIND_INVALID"):
        pe.check_trace(script, dict(ok, BUILD="porque sí"), tmp_path, tmp_path, "req-9")
    with pytest.raises(pe.ExamBlocked, match="EXAM_TRACE_REQUEST_MISMATCH"):
        pe.check_trace(script, dict(ok, MESSAGE_="request:req-8"), tmp_path, tmp_path, "req-9")


def test_reference_patch_applies_to_base(tmp_path):
    wt = tmp_path / "wt"
    (wt / "src").mkdir(parents=True)
    (wt / "src/A.java").write_text("old\n")
    subprocess.run(["git", "init", "-q"], cwd=wt, check=True)
    subprocess.run(["git", "add", "."], cwd=wt, check=True)
    ref = tmp_path / "ref"
    (ref / "src").mkdir(parents=True)
    (ref / "src/A.java").write_text("new\n")
    (ref / "src/B.java").write_text("added\n")
    patch = pe.reference_patch(wt, ref)
    assert c.changed_paths(patch) == ["src/A.java", "src/B.java"]
    pf = tmp_path / "p.patch"
    pf.write_text(patch)
    subprocess.run(["git", "apply", "--check", str(pf)], cwd=wt, check=True)
    pkg = json.loads(pe.reference_package("req9backend2", b"exam", patch))
    assert c.parse_reference(json.dumps(pkg).encode(), "req9backend2", pkg["holdout_sha256"]) == patch


def test_no_workflow_has_duplicate_keys():
    """T40.2: GitHub rejects duplicated mapping keys that PyYAML silently merges."""
    import yaml

    class Strict(yaml.SafeLoader):
        pass

    def mapping(loader, node, deep=False):
        keys = [loader.construct_object(k, deep=deep) for k, _ in node.value]
        dup = {k for k in keys if keys.count(k) > 1}
        assert not dup, f"duplicate keys {dup} at line {node.start_mark.line + 1}"
        return yaml.SafeLoader.construct_mapping(loader, node, deep)

    Strict.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
    for wf in sorted((ROOT / ".github/workflows").glob("*.yml")):
        yaml.load(wf.read_text("utf-8"), Loader=Strict)


def test_rehearsal_reports_only_visible_failed_command_names():
    from pilot.worker_v08.native_exam_control import visible_failures
    receipt = {"attempts": [{"acceptance": [
        {"name": "backend-package", "status": "PASS"},
        {"name": "backend-contract-live", "status": "FAIL", "stdout": "secret detail"}]}],
        "hidden_oracle": {"status": "FAIL", "name": "holdout"}}
    assert visible_failures(receipt) == ["backend-contract-live"]
    assert visible_failures({}) == []
    assert visible_failures({"attempts": []}) == []


def test_rehearsal_reports_reference_patch_rejection_category_and_path():
    from pilot.worker_v08.native_exam_control import patch_rejection
    receipt = {"attempts": [{"proposal_reason": "PATCH_REJECTED: cumulative path is protected: a/B.java",
                             "acceptance": []}]}
    assert patch_rejection(receipt) == "PATCH_REJECTED: cumulative path is protected: a/B.java"
    assert patch_rejection({"attempts": [{"proposal_reason": "PATCH_APPLIED_IN_DISPOSABLE_WORKSPACE"}]}) is None
