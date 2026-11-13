"""T4 admission and re-registration tests (offline; no examiner data)."""
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from t4_admission import (AdmissionBlocked, require_green_base, missing_exam,
                          public_exam_request, incremental_task, registration_variant)


SHA = "a" * 40
SOURCE = "b" * 64


def workflow(status="completed", conclusion="success", sha=SHA, created="2026-11-13"):
    return {"head_sha": sha, "head_branch": "main", "event": "push",
            "status": status, "conclusion": conclusion, "run_attempt": 1,
            "created_at": created, "id": 15}


def test_base_ci_requires_green_exact_sha_and_latest_run():
    require_green_base(SHA, lambda _: {"total_count": 1,
                                       "workflow_runs": [workflow()]})
    for payload in (
        {"total_count": 0, "workflow_runs": []},
        {"total_count": 1, "workflow_runs": [workflow(sha="c" * 40)]},
        {"total_count": 1, "workflow_runs": [workflow(conclusion="failure")]},
        {"total_count": 1, "workflow_runs": [workflow(status="in_progress", conclusion=None)]},
        {"total_count": 101, "workflow_runs": [workflow()]},
        {"total_count": 2, "workflow_runs": [
            workflow(), workflow(conclusion="failure", created="2026-11-14")]},
    ):
        with pytest.raises(AdmissionBlocked, match="BASE_NO_VERDE"):
            require_green_base(SHA, lambda _, p=payload: p)
    with pytest.raises(AdmissionBlocked, match="BASE_NO_VERDE"):
        require_green_base("invalid", lambda _: {})


def test_missing_ciphertext_checks_existence_only(tmp_path):
    assert missing_exam(tmp_path, "sampletask")
    directory = tmp_path / "pilot/holdouts"
    directory.mkdir(parents=True)
    path = directory / "sampletask.oracle.json.age"
    path.write_bytes(b"opaque")
    assert not missing_exam(tmp_path, "sampletask")
    path.unlink()
    path.symlink_to(tmp_path / "not-present")
    with pytest.raises(AdmissionBlocked, match="EXAMEN_PENDIENTE"):
        missing_exam(tmp_path, "sampletask")


def test_request_public_task_and_contract_skeleton(tmp_path):
    path = tmp_path / "pilot/runs/sample/templates/sampletask.task.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"task_spec": {
        "write_path_patterns": ["apps/time-service/src/main/java/example/Example.java"],
        "context_path_patterns": []}}))
    binding = {"task_name": "sampletask", "template_path": str(path.relative_to(tmp_path))}
    lot = {"id": "SOL-001", "area": "BACKEND",
           "requirement_ids": ["REQ-CUSTOM-1"]}
    title, body = public_exam_request(tmp_path, "sample", binding, lot)
    assert title == "EXAM_REQUEST: sampletask"
    assert "REQ-CUSTOM-1" in body
    assert "T4_PUBLIC_TASK_SKELETON_V1" in body
    assert "key" not in body.lower()
    file = tmp_path / "contracts/catalog.skeleton.json"
    file.parent.mkdir()
    file.write_text(json.dumps({"schema_version": "T2_CONTRACT_SKELETON_V1",
        "functional_module": "catalog", "fields": [], "errors": [],
        "rules": [], "requirement_ids": ["REQ-CUSTOM-1"]}))
    path.write_text(json.dumps({"task_spec": {
        "write_path_patterns": ["contracts/catalog.openapi.yaml"],
        "context_path_patterns": ["contracts/catalog.skeleton.json"]}}))
    _, body = public_exam_request(tmp_path, "sample", binding, lot)
    assert "T2_CONTRACT_SKELETON_V1" in body
    assert "catalog" in body


def test_incremental_suffix_without_overwrite():
    assert incremental_task("sampler", set()) == "sampler"
    assert incremental_task("sampler", {"sampler"}) == "sampler2"
    assert incremental_task("sampler", {"sampler", "sampler2"}) == "sampler3"


def test_variant_changes_only_if_source_or_pack_changes(tmp_path):
    directory = tmp_path / "pilot/worker_v08/native_tasks"
    directory.mkdir(parents=True)
    template = tmp_path / "pilot/runs/sample/templates/sampler.task.json"
    template.parent.mkdir(parents=True)
    wanted = {"objective": "Implement the feature",
              "write_path_patterns": ["frontend/src/demo.ts"]}
    template.write_text(json.dumps({"task_spec": wanted}))
    assert registration_variant(tmp_path, "sampler",
                                str(template.relative_to(tmp_path)), SOURCE) == "sampler"
    (directory / "sampler.json").write_text(json.dumps({
        "task_spec": {**wanted, "source_snapshot_sha256": SOURCE}}))
    assert registration_variant(tmp_path, "sampler",
                                str(template.relative_to(tmp_path)), SOURCE) is None
    changed = "c" * 64
    assert registration_variant(tmp_path, "sampler",
                                str(template.relative_to(tmp_path)), changed) == "sampler2"
    (directory / "sampler2.json").write_text(json.dumps({
        "task_spec": {**wanted, "source_snapshot_sha256": changed}}))
    assert registration_variant(tmp_path, "sampler",
                                str(template.relative_to(tmp_path)), changed) is None
    template.write_text(json.dumps({"task_spec": {**wanted, "objective": "Changed"}}))
    assert registration_variant(tmp_path, "sampler",
                                str(template.relative_to(tmp_path)), changed) == "sampler3"
