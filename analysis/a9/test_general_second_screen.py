"""General T1-A acceptance: unrelated codes and independent pinned screen source.

This screen is a deliberately simulated A9 intake candidate. It does not
claim its A1-A8 stage trace is an attested Analysis run.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil

import pytest

from analysis.a9.front_bindings import FrontBindingGap, partition
from analysis.a9.area_projection import project
from pilot.orchestrator import intake
from pilot.orchestrator.package_to_lots import prepare

SOURCE = Path(__file__).resolve().parents[1] / "fixtures/demo_notes_edit"


def second_screen():
    raw = (SOURCE / "source.json").read_bytes()
    pin = json.loads((SOURCE / "SOURCE_PIN.json").read_text())
    assert pin["fixture_id"] == "DEMO-NOTES-EDIT"
    assert pin["schema_version"] == "SOURCE_SCREEN_PIN_V1"
    assert pin["sha256"] == hashlib.sha256(raw).hexdigest()
    result = json.loads(raw)
    assert result["target_ref"] == pin["fixture_id"]
    return result


def front(candidate, *, obligation_refs=(), kind="OTHER"):
    return {
        "front_id": "F3-" + hashlib.sha256(candidate.encode()).hexdigest()[:16],
        "candidate_ref": candidate, "front_kind": kind,
        "evidence_refs": [candidate], "obligation_refs": list(obligation_refs),
        "status": "REQUIRED", "closure": "CLOSED", "blockers": [],
        "reason": "Fixture source evidence", "simulation_mode": "SIMULATED_SANDBOX_ONLY",
    }


def inputs(source):
    scope = source["target_ref"]
    screen = source["screen_contract"]
    base = "fixture://demo_notes_edit/screen#contract/"
    fronts = [
        front(base + "fields/" + str(i), kind="DATA_CONTRACT")
        for i, _ in enumerate(screen["fields"])
    ] + [
        front(base + "errors/" + str(i), kind="STATE_ERROR")
        for i, _ in enumerate(screen["errors"])
    ] + [
        front(base + "visual/variants/" + str(i), kind="UI_VISUAL")
        for i, _ in enumerate(screen["visual"]["variants"])
    ] + [
        front(base + "context"), front(base + "metadata"),
    ] + [
        front(r["evidence_refs"][0], obligation_refs=[r["source_requirement_id"]],
              kind="SECURITY_PRIVACY" if source["effective_rules"][r["source_requirement_id"]]["categoria"] == "security" else "OTHER")
        for r in source["requirements"]
    ]
    requirements = [
        {**deepcopy(r), "scope_id": scope, "materiality_level": "HIGH",
         "requires_independent_exam": True, "simulation_mode": "SIMULATED_SANDBOX_ONLY"}
        for r in source["requirements"]
    ]
    return fronts, requirements


def make_package(source, request):
    original_fronts, requirements = inputs(source)
    active, excluded = partition(
        original_fronts, requirements, source["screen_contract"],
        source["effective_rules"], scope=source["target_ref"],
        create_empty_inventory=True)
    projected, active, scopes, rule_fronts = project(
        source["target_ref"], requirements, active, readiness="READY_CANDIDATE")
    return {
        "schema_version": "ANALYSIS_IMPLEMENTATION_PACKAGE_V1",
        "candidate_only": True, "analysis_mode": "SIMULATED_ANALYSIS",
        "request_sha256": hashlib.sha256(intake.normalized_request_bytes(request)).hexdigest(),
        "request_context": {
            "intent": request.decode().strip(),
            "target_ref": source["target_ref"],
            "simulation_mode": "SIMULATED_SANDBOX_ONLY",
        },
        "classification": {
            "target_granularity": "SCREEN", "depth": "L2",
            "authority_state": "NEW", "implementation_state": "NEW",
        },
        "stage_trace": [{
            "stage": "A" + str(i), "status": "SIMULATED_CANDIDATE",
            "source_refs": ["fixture://demo_notes_edit/source.json@" +
                            hashlib.sha256((SOURCE / "source.json").read_bytes()).hexdigest()],
        } for i in range(1, 10)],
        "material_unknowns": [], "decisions_pending": [],
        "requirements": projected, "material_fronts": active,
        "applicable_rules": [{
            "rule_code": row["source_requirement_id"],
            "requirement_id": row["requirement_id"],
            "front_id": rule_fronts[row["source_requirement_id"]],
            "source_ref": row["evidence_refs"][0],
        } for row in projected if not row.get("derived_from_requirement_id")],
        "scope_proposals": scopes,
        "non_atomized_fronts": excluded,
        "research_stop": {
            "decision": "STOP", "decision_stable": True,
            "all_material_fronts_accounted": True,
            "unresolved_decision_changing_questions": [],
        },
        "package_readiness_candidate": "READY_CANDIDATE",
        "production_authority": False, "handoff_allowed": False,
        "downstream_authorized": False, "pg01_consumer_verified": False,
    }


def test_second_screen_source_explicit_not_prefix_based():
    source = second_screen()
    active, excluded = partition(*inputs(source), source["screen_contract"],
                                 source["effective_rules"], scope=source["target_ref"],
                                 create_empty_inventory=True)
    assert [x["execution_area"] for x in active] == ["BACKEND", "FRONTEND"]
    assert any(x["reason"] == "SOURCE_SECTION_HAS_NO_OBLIGATION" for x in excluded)
    assert len(source["screen_contract"]["policies"]) == 1
    assert source["screen_contract"]["fields"][0]["field_code"] != source["screen_contract"]["rules"][0]["code"]


def test_second_screen_missing_link_blocks_with_exact_reason():
    source = second_screen()
    source["screen_contract"]["fields"][0].pop("rule_refs")
    with pytest.raises(FrontBindingGap, match="A9_SECTION_RULE_REFS_MISSING:fields/0"):
        partition(*inputs(source), source["screen_contract"],
                  source["effective_rules"], scope=source["target_ref"],
                  create_empty_inventory=True)


@pytest.mark.skipif(os.getenv("SELECTOR_EXP_DISPOSABLE_DB") != "YES"
                    or not os.getenv("SELECTOR_EXP_TEST_DSN"),
                    reason="Requires disposable SQL profile selector")
def test_second_screen_produces_two_lots_without_manual_decision(tmp_path):
    source = second_screen()
    raw = b"Create a notes editor with independently sourced rules and policies\n"
    package = make_package(source, raw)
    slug = "t1a-notes"
    folder = tmp_path / "pilot/runs" / slug
    folder.mkdir(parents=True)
    (folder / "request.md").write_bytes(raw)
    (folder / "analysis.json").write_bytes(intake.canonical(package))
    state = intake.accept(tmp_path, slug)
    assert state["stage"] == "INTAKE_ACCEPTED"
    assert not (folder / "owner_area_decision.json").exists()
    assert not (folder / "planning_fixture.json").exists()
    lots = prepare(tmp_path, slug, base_head_sha="a" * 40)
    assert [r["area"] for r in lots["lots"]] == ["BACKEND", "FRONTEND"]
    assert len(lots["lots"]) == 2
    assert lots["lots"][1]["depends_on"] == [lots["lots"][0]["id"]]
    assert (folder / "lots.json").is_file()
    assert (folder / "t1_interventions.json").is_file()
    assert json.loads((folder / "t1_interventions.json").read_text())["INTERVENCION_MANUAL"] == "NO"
    if os.getenv("T1A_ARTIFACT_DIR"):
        shutil.copytree(folder, Path(os.environ["T1A_ARTIFACT_DIR"]) / "notes")
