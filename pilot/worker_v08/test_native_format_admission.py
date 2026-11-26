"""Offline integration tests of format admission and workflow."""
import json
from pathlib import Path

import pytest

import native_format_admission as a
from native_format_preflight import FormatResult

ROOT = Path(__file__).resolve().parents[2]
SHA = "a" * 40
JAVA = "service/src/main/java/Example.java"
COORD = JAVA + ": original line 78, 8 lines; formatted line 78, 7 lines"


@pytest.mark.parametrize("status,reason,proceed", [
    ("PASS", "FORMAT_OK", True),
    ("SKIPPED", "NO_REGISTERED_FORMAT_COMMAND", True),
    ("FORMAT_FAIL", "SPOTLESS_VIOLATIONS", False),
    ("BASELINE_FAIL", "SPOTLESS_BASELINE_VIOLATIONS", False),
    ("INVALID_PROPOSAL", "FORMAT_TASK_PACK_MISMATCH", False),
    ("INFRA_ERROR", "FORMAT_TOTAL_TIMEOUT", False),
])
def test_admission(tmp_path, monkeypatch, status, reason, proceed):
    result = FormatResult(status, reason, paths=(JAVA,), diagnostics=(COORD,)) if status == "FORMAT_FAIL" else FormatResult(status, reason)
    monkeypatch.setattr(a, "_evaluate", lambda *args: result)
    monkeypatch.setattr(a, "checkout_identity", lambda *args: dict.fromkeys(("task_pack_sha256", "proposal_sha256", "patch_sha256"), "b"*64))
    out = tmp_path / "result"
    assert a.admit(tmp_path, tmp_path, tmp_path, "synthetic", SHA, 2, 42, out) is proceed
    evidence = json.loads((out / "format-result.json").read_text())
    assert evidence["status"] == status and evidence["reason"] == reason
    assert evidence["functional_attempt_consumed"] is False
    assert evidence["proposal_commit_sha"] == SHA and evidence["run_id"] == 42
    assert not (out / "attempt-proof.json").exists()
    assert (out / "no-attempt.json").exists() is not proceed
    if not proceed:
        assert json.loads((out / "no-attempt.json").read_text()) == {
            "schema_version": "LF_NATIVE_NO_ATTEMPT_V1", "task_id": "synthetic",
            "run_id": 42, "attempt": 2, "reason": "PRE_ATTEMPT",
        }


def test_invalid_public_payload():
    assert a._public(FormatResult("FORMAT_FAIL", "SPOTLESS_VIOLATIONS", paths=(JAVA,),
                                 diagnostics=("untrusted output",)))["status"] == "INFRA_ERROR"


def test_pack_before_format(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(a, "load_registration", lambda *args: ({}, "unused"))
    monkeypatch.setattr(a, "parse_worker_task", lambda x: object())
    monkeypatch.setattr(a, "read_proposal_envelope", lambda *args: {"proposal": {}})
    monkeypatch.setattr(a, "parse_patch_proposal", lambda *args: object())
    monkeypatch.setattr(a, "inspect_patch", lambda *args: calls.append("scope"))
    monkeypatch.setattr(a, "_check_pack", lambda *args, **kw: calls.append("pack") or False)
    monkeypatch.setattr(a, "prevalidate", lambda *args: pytest.fail("format before pack"))
    assert a._evaluate(tmp_path, tmp_path, tmp_path, "synthetic", SHA, 1, False).status == "INVALID_PROPOSAL"
    assert calls == ["scope", "pack"]


def test_exact_pack_hash(tmp_path, monkeypatch):
    monkeypatch.setattr(a, "export", lambda *args: "b" * 64)
    args = (tmp_path, tmp_path, "synthetic", {})
    assert a._check_pack(*args, {"task_pack_sha256": "b" * 64}, route_retry=False, sha=SHA, attempt=1)
    assert not a._check_pack(*args, {"task_pack_sha256": "c" * 64}, route_retry=False, sha=SHA, attempt=1)


def test_workflow_order_and_isolation():
    text = (ROOT / ".github/workflows/worker-native.yml").read_text()
    gate = text.split("      - name: Prevalidate native proposal format before examiner material\n", 1)[1].split("\n      - name:", 1)[0]
    assert "env -i" in gate and "native_format_admission.py" in gate
    assert "GH_TOKEN" not in gate and "GITHUB_TOKEN" not in gate and "secrets" not in gate
    assert "continue-on-error" not in gate
    assert text.index("Determine and gate attempt") < text.index("Verify exact proposal checkout HEAD") < text.index("Prevalidate native proposal format")
    assert text.index("Prevalidate native proposal format") < text.index("Install age v1.3.2") < text.index("Decode task-selected external oracle") < text.index("Execute original run_verified_worker")
    assert "name: native-format-preflight" in text
    assert "steps.format.outcome == 'failure'" in text
    assert "native-format-public/no-attempt.json" in text
    assert text.count("name: native-attempt-proof") == 1
    assert text.count("name: native-no-attempt") == 1
