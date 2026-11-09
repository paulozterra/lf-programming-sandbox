"""Offline S1 tests against the unchanged vendored Worker (no API or oracle)."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "vendor/programming-agent/src"))

from programming_agent_runner.hashutil import canonical_json_bytes, source_snapshot_sha256
from programming_agent_runner.model_client import ModelError
from programming_agent_runner.worker_spec import parse_worker_task
from native_capture_client import NativeCaptureClient, task_pack_bytes
from native_proposal_client import NativeProposalClient
from native_attempt_guard import validate_attempt_history
from export_task_pack import export


def cmd(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def make_repo(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    cmd(repo, "config", "user.email", "test@example.invalid")
    cmd(repo, "config", "user.name", "Offline Test")
    (repo / "README.md").write_text("A sample file\\n", encoding="utf-8")
    cmd(repo, "add", "README.md")
    cmd(repo, "commit", "-qm", "fixture")
    spec = {
        "schema_version": 1, "task_id": "LF-NATIVE-TEST",
        "objective": "Modify README according to the task",
        "base_head_sha": cmd(repo, "rev-parse", "HEAD"),
        "source_snapshot_sha256": source_snapshot_sha256(repo),
        "context_path_patterns": ["README.md"],
        "write_path_patterns": ["README.md"],
        "protected_path_patterns": [],
        "acceptance_commands": [{
            "name": "visible", "argv": ["python3", "-c", "print('ok')"],
            "timeout_seconds": 15, "max_output_bytes": 1024
        }],
        "max_attempts": 1, "max_patch_bytes": 12000,
        "max_changed_files": 1, "max_context_bytes": 10000,
        "allow_deletions": False
    }
    spec_path = tmp_path / "task.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    parse_worker_task(spec)  # ensures the fixture satisfies the vendored contract
    return repo, spec_path


def envelope(pack_sha: str, proposal: dict) -> dict:
    return {
        "task_pack_sha256": pack_sha,
        "proposal_sha256": hashlib.sha256(canonical_json_bytes(proposal)).hexdigest(),
        "proposal": proposal,
        "author": "GPT_NATIVE",
    }


def test_capture_is_original_worker_payload_and_deterministic(tmp_path):
    repo, spec_path = make_repo(tmp_path)
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    sha1 = export(repo, spec_path, first)
    sha2 = export(repo, spec_path, second)
    assert sha1 == sha2
    assert first.read_bytes() == second.read_bytes()
    pack = json.loads(first.read_text(encoding="utf-8"))
    assert set(pack) == {"system_instruction", "user_payload"}
    assert pack["user_payload"]["attempt"] == 1
    assert pack["user_payload"]["previous_feedback"] is None
    assert pack["user_payload"]["task"]["base_head_sha"] == cmd(repo, "rev-parse", "HEAD")
    assert first.read_bytes() == task_pack_bytes(**pack)
    assert not any(k in pack for k in ("oracle", "holdout", "hidden_oracle"))
    assert not (tmp_path / "hidden-oracle.json").exists()


def test_capture_stops_no_model_calls_and_never_overwrites(tmp_path):
    client = NativeCaptureClient(tmp_path / "pack.json")
    with pytest.raises(ModelError, match="NATIVE_CAPTURE_ONLY"):
        client.generate("instruction", {"task": "fixture"})
    with pytest.raises(ModelError, match="NATIVE_CAPTURE_ALREADY_EXISTS"):
        client.generate("instruction", {"task": "fixture"})
    assert client.captured_sha256 == hashlib.sha256((tmp_path / "pack.json").read_bytes()).hexdigest()


def test_native_client_exact_pack_sha_and_empty_usage(tmp_path):
    instruction = "system"
    payload = {"task": {"base_head_sha": "a" * 40}, "attempt": 1}
    pack_sha = hashlib.sha256(task_pack_bytes(instruction, payload)).hexdigest()
    proposal = {"schema_version": 1, "summary": "Test only", "patch": "diff --git a/x b/x\\n",
                "changed_paths": ["x"]}
    file = tmp_path / "proposal.json"
    file.write_bytes(canonical_json_bytes(envelope(pack_sha, proposal)))
    response = NativeProposalClient(file).generate(instruction, payload)
    assert response.usage == {}
    assert response.response_id == hashlib.sha256(canonical_json_bytes(proposal)).hexdigest()
    assert json.loads(response.output_text) == proposal


@pytest.mark.parametrize("tamper", ["task", "head", "context", "instruction"])
def test_pack_drift_fail_closed(tmp_path, tamper):
    instruction = "system"
    payload = {"task": {"base_head_sha": "a" * 40}, "workspace": {"files": []}}
    pack_sha = hashlib.sha256(task_pack_bytes(instruction, payload)).hexdigest()
    proposal = {"schema_version": 1, "summary": "Test", "patch": "x", "changed_paths": ["x"]}
    file = tmp_path / "proposal.json"
    file.write_bytes(canonical_json_bytes(envelope(pack_sha, proposal)))
    changed = json.loads(json.dumps(payload))
    changed_system = instruction
    if tamper == "task":
        changed["task"]["task_id"] = "another-task"
    elif tamper == "head":
        changed["task"]["base_head_sha"] = "b" * 40
    elif tamper == "context":
        changed["workspace"]["files"] = [{"path": "README.md", "content": "tampered"}]
    else:
        changed_system = "altered system instruction"
    with pytest.raises(ModelError, match="NATIVE_PACK_MISMATCH"):
        NativeProposalClient(file).generate(changed_system, changed)


def test_tampered_proposal_sha_blocks(tmp_path):
    p = tmp_path / "proposal.json"
    raw = envelope("a" * 64, {"patch": "x"})
    raw["proposal_sha256"] = "b" * 64
    p.write_bytes(canonical_json_bytes(raw))
    with pytest.raises(ModelError, match="NATIVE_PROPOSAL_SHA_MISMATCH"):
        NativeProposalClient(p).generate("x", {})


def test_attempt_guard_three_runs_and_trusted_history():
    history = [
        {"task_id": "ex6", "attempt": i, "task_pack_sha256": f"{i:064x}", "run_id": i}
        for i in (1, 2)
    ]
    validate_attempt_history("ex6", 3, history)
    with pytest.raises(ValueError, match="NATIVE_ATTEMPT"):
        validate_attempt_history("ex6", 4, history)
    with pytest.raises(ValueError, match="NATIVE_ATTEMPT"):
        validate_attempt_history("ex6", 3, history[:1])
    with pytest.raises(ValueError, match="NATIVE_ATTEMPT"):
        validate_attempt_history("other-task", 3, history)
