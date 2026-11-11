"""Offline CP3.2: no model, Supabase, hidden exam, or real authority."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pilot/orchestrator"))
import intake

NAME = "sample-reminder-note"
FIXTURE = ROOT / "pilot/runs" / NAME


def setup(tmp_path):
    folder = tmp_path / "pilot/runs" / NAME
    folder.mkdir(parents=True)
    for name in ("request.md", "analysis.json"):
        shutil.copyfile(FIXTURE / name, folder / name)
    return folder


def mutate(folder, callback):
    p = folder / "analysis.json"
    obj = json.loads(p.read_text(encoding="utf-8"))
    callback(obj)
    p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def test_valid_intake_uses_pinned_pg01_as_unattested_fixture(tmp_path):
    folder = setup(tmp_path)
    state = intake.accept(tmp_path, NAME)
    assert state["stage"] == "INTAKE_ACCEPTED"
    assert state["pg01"]["status"] == "FIXTURE_UNATTESTED"
    assert state["pg01"]["verified"] is False
    assert state["pg01"]["producer"] == "pg01_technical_frame_v3_candidate_v1.preflight"
    assert state["pg01"]["reason"] == "PG01_V3_EVIDENCE_MISSING"
    assert (folder / "state.json").read_bytes() == intake.canonical(state)
    assert hashlib.sha256((folder / "request.md").read_bytes()).hexdigest() == state["request_sha256"]


def test_same_request_produces_identical_state_bytes(tmp_path):
    first = tmp_path / "one"
    second = tmp_path / "two"
    one = setup(first)
    two = setup(second)
    intake.accept(first, NAME)
    initial = (one / "state.json").read_bytes()
    intake.accept(second, NAME)
    assert initial == (two / "state.json").read_bytes()
    intake.accept(first, NAME)
    assert initial == (one / "state.json").read_bytes()


@pytest.mark.parametrize("modification,expected", [
    (lambda x: x.pop("analysis_mode"), "ANALYSIS_SIMULATION_MARK_MISSING"),
    (lambda x: x.update(analysis_mode="REAL_ANALYSIS"), "ANALYSIS_SIMULATION_MARK_MISSING"),
    (lambda x: x.update(request_sha256="0" * 64), "ANALYSIS_REQUEST_SHA_MISMATCH"),
    (lambda x: x.pop("requirements"), "ANALYSIS_FIELDS_MISSING"),
    (lambda x: x.pop("material_fronts"), "ANALYSIS_FIELDS_MISSING"),
    (lambda x: x.pop("classification"), "ANALYSIS_FIELDS_MISSING"),
    (lambda x: x["requirements"].append(copy.deepcopy(x["requirements"][0])), "ANALYSIS_REQUIREMENT_DUPLICATED"),
    (lambda x: x["requirements"].clear(), "ANALYSIS_FIELDS_MISSING"),
    (lambda x: x["material_fronts"].append({
        "front_id": "A7-FRONT-WITHOUT-REQ", "scope_ids": ["SCOPE-EMPTY"],
        "obligation_mode": "REQUIRED", "closure": "BLOCKED",
        "blockers": ["FIXTURE_UNATTESTED"], "evidence_refs": [], "reason": "No requirement"}), "ANALYSIS_FRONT_UNKNOWN_SCOPE"),
    (lambda x: x["scope_proposals"].append({
        "scope_id": "SCOPE-EMPTY", "readiness_candidate": "BLOCKED",
        "material_front_refs": ["A7-FRONT-EMPTY"], "blockers": ["FIXTURE_UNATTESTED"]}), "ANALYSIS_FRONT_WITHOUT_REQUIREMENT"),
    (lambda x: x.update(production_authority=True), "INTAKE_AUTHORITY_FORBIDDEN"),
    (lambda x: x["scope_proposals"][0].update(handoff_allowed=True), "INTAKE_AUTHORITY_FORBIDDEN"),
])
def test_fail_closed_cases(tmp_path, modification, expected):
    folder = setup(tmp_path)
    mutate(folder, modification)
    with pytest.raises(intake.IntakeBlocked, match=expected):
        intake.accept(tmp_path, NAME)
    assert not (folder / "state.json").exists()


def test_front_without_requirement_blocks(tmp_path):
    folder = setup(tmp_path)
    def bad(x):
        x["requirements"] = [dict(req, scope_id="SCOPE-OTHER") for req in x["requirements"]]
    mutate(folder, bad)
    with pytest.raises(intake.IntakeBlocked, match="ANALYSIS_REQUIREMENT_SCOPE_INVALID"):
        intake.accept(tmp_path, NAME)


def test_request_lf_normalization_and_sha_mismatch(tmp_path):
    folder = setup(tmp_path)
    original = (folder / "request.md").read_bytes()
    (folder / "request.md").write_bytes(original.replace(b"\\n", b"\\r\\n"))
    assert intake.accept(tmp_path, NAME)["request_sha256"] == hashlib.sha256(original).hexdigest()
    (folder / "request.md").write_bytes(original + b"extra\\n")
    with pytest.raises(intake.IntakeBlocked, match="ANALYSIS_REQUEST_SHA_MISMATCH"):
        intake.accept(tmp_path, NAME)


def test_state_tampering_blocks_replay(tmp_path):
    folder = setup(tmp_path)
    intake.accept(tmp_path, NAME)
    (folder / "state.json").write_bytes(b"{}")
    with pytest.raises(intake.IntakeBlocked, match="INTAKE_STATE_DRIFT"):
        intake.accept(tmp_path, NAME)


def test_never_emits_true_authority_flags(tmp_path):
    setup(tmp_path)
    result = intake.accept(tmp_path, NAME)
    assert result["production_authority"] is False
    assert result["handoff_allowed"] is False
    assert result["downstream_authorized"] is False
    assert result["pg01_consumer_verified"] is False
    assert result["pg01"]["verified"] is False
    assert all(value is not True for key, value in result.items()
               if key.endswith("_authority") or key in intake.AUTHORITY)


def test_invalid_run_id_and_symlink_input_block(tmp_path):
    with pytest.raises(intake.IntakeBlocked, match="RUN_ID_INVALID"):
        intake.accept(tmp_path, "../hidden")
    folder = setup(tmp_path)
    target = folder / "request.md"
    target.unlink()
    target.symlink_to(FIXTURE / "request.md")
    with pytest.raises(intake.IntakeBlocked, match="INTAKE_INPUT_MISSING"):
        intake.accept(tmp_path, NAME)
