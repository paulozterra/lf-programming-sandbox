"""F4 A9 real intake compatibility and fail-closed negative evidence."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import pytest

from analysis.a9.package import build, validate, fail
from analysis.host.run_a1_a8_fixture import run_f3
from analysis.host.run_a1_a9_fixture import run_f4
from analysis.host.run_a1_a5_fixture import REQUEST
from analysis.host.simulated_admission_gate import AdmissionBlocked
from pilot.orchestrator import intake


@pytest.fixture(scope="module")
def upstream():
    return run_f3()


@pytest.fixture(scope="module")
def payload(upstream):
    from analysis.host.run_a1_a9_fixture import make_rule_sources
    upstream["rule_sources"] = make_rule_sources()
    return build(upstream, (REQUEST + "\n").encode("utf-8"))


def assert_rejected(package, raw, expected, *, from_a9=False):
    error = AdmissionBlocked if from_a9 else intake.IntakeBlocked
    with pytest.raises(error) as e:
        (validate if from_a9 else intake.validate)(package, raw)
    assert str(e.value) == expected


def test_login_real_intake_validate_and_accept(tmp_path):
    result = run_f4(tmp_path)
    package = result["package"]
    state = result["state"]
    raw = (tmp_path / "pilot/runs/f4-login/request.md").read_bytes()
    saved = json.loads((tmp_path / "pilot/runs/f4-login/analysis.json").read_text())
    assert saved == package
    assert intake.validate(saved, raw)[1] == state["request_sha256"]
    assert state["stage"] == "INTAKE_ACCEPTED"
    assert state["pg01"]["status"] == "FIXTURE_UNATTESTED"
    assert state["pg01"]["verified"] is False
    assert state["pg01_consumer_verified"] is False
    assert result["slug"] == "f4-login"
    assert intake.accept(tmp_path, "f4-login") == state


def test_six_rules_exclusions_parity(payload, upstream):
    rows = [r for r in payload["requirements"] if not r.get("derived_from_requirement_id")]
    assert len(rows) == 6
    assert {x["source_requirement_id"] for x in rows} == {
        x["rule_code"] for x in upstream["stages"]["A3"]["policy_scope_clear_rule_candidates"]}
    assert "REQ-SBX-R-PENDING" not in {x["requirement_id"] for x in rows}
    assert "REQ-SBX-R-CAND" not in {x["requirement_id"] for x in rows}
    by_source = {x["source_requirement_id"]: x for x in rows}
    for rule in upstream["stages"]["A3"]["policy_scope_clear_rule_candidates"]:
        assert rule["source_ref"] in by_source[rule["rule_code"]]["evidence_refs"]
    assert len(next(x for x in rows if x["requirement_id"] == "REQ-SBX-R-ERR")["acceptance_checks"]) == 2


def test_material_front_scope_source_split_is_ready(payload):
    assert payload["scope_proposals"][0]["readiness_candidate"] == "READY_CANDIDATE"
    assert payload["package_readiness_candidate"] == "READY_CANDIDATE"
    assert [f["execution_area"] for f in payload["material_fronts"]] == ["BACKEND", "FRONTEND"]
    assert all(f["requirement_ids"] and f["execution_area_source_ref"]
               for f in payload["material_fronts"])
    assert all(f["obligation_mode"] == "NOT_APPLICABLE"
               for f in payload["non_atomized_fronts"])
    assert any(f["reason"] == "SOURCE_SECTION_HAS_NO_OBLIGATION"
               for f in payload["non_atomized_fronts"])
    assert {scope["scope_id"] for scope in payload["scope_proposals"]} == {
        "SBX-AUTH-LOGIN-BACKEND", "SBX-AUTH-LOGIN-FRONTEND"}
    assert {fid for scope in payload["scope_proposals"]
            for fid in scope["material_front_refs"]} == {
        f["front_id"] for f in payload["material_fronts"]}
    assert all(f["scope_ids"] == ["SBX-AUTH-LOGIN-" + f["execution_area"]]
               for f in payload["material_fronts"])
    assert len({r["requirement_id"] for r in payload["requirements"]}) == len(payload["requirements"])
    assert all(r["derived_from_requirement_id"] in {
        source["requirement_id"] for source in payload["requirements"]
        if "derived_from_requirement_id" not in source}
        for r in payload["requirements"] if "derived_from_requirement_id" in r)
    assert payload["research_stop"]["decision"] == "STOP"


def test_intake_requirement_missing_acceptance(payload):
    p = deepcopy(payload)
    p["requirements"][0].pop("acceptance_signal")
    assert_rejected(p, (REQUEST+"\n").encode(), "ANALYSIS_FIELDS_MISSING")


def test_intake_scope_without_fronts(payload):
    p = deepcopy(payload)
    p["scope_proposals"][0]["material_front_refs"] = []
    assert_rejected(p, (REQUEST+"\n").encode(), "ANALYSIS_FRONT_SCOPE_MISMATCH")


def test_intake_front_unknown_scope(payload):
    p = deepcopy(payload)
    p["material_fronts"][0]["scope_ids"] = ["NOT-A-SCOPE"]
    assert_rejected(p, (REQUEST+"\n").encode(), "ANALYSIS_FRONT_UNKNOWN_SCOPE")


def test_intake_wrong_request_sha(payload):
    assert_rejected(payload, b"Otro pedido\n", "ANALYSIS_REQUEST_SHA_MISMATCH")


def test_intake_authority_true(payload):
    p = deepcopy(payload)
    p["production_authority"] = True
    assert_rejected(p, (REQUEST+"\n").encode(), "INTAKE_AUTHORITY_FORBIDDEN")


def test_intake_missing_stage(payload):
    p = deepcopy(payload)
    p["stage_trace"].pop()
    assert_rejected(p, (REQUEST+"\n").encode(), "ANALYSIS_FIELDS_MISSING")


def test_a9_ready_with_blocked_front(payload):
    p = deepcopy(payload)
    p["material_fronts"][0]["closure"] = "BLOCKED"
    p["material_fronts"][0]["blockers"] = ["F4_NEGATIVE"]
    p["scope_proposals"][0]["readiness_candidate"] = "READY_CANDIDATE"
    p["package_readiness_candidate"] = "READY_CANDIDATE"
    assert_rejected(p, (REQUEST+"\n").encode(), "F4_A9_READY_WITH_BLOCKED_FRONT", from_a9=True)


def test_a9_missing_required_material(payload):
    p = deepcopy(payload)
    p.pop("programming_context_snapshot")
    assert_rejected(p, (REQUEST+"\n").encode(), "F4_A9_FIELD_MISSING", from_a9=True)


def test_a9_snapshot_fingerprint_changed(payload):
    p = deepcopy(payload)
    p["programming_context_snapshot"]["source_snapshot_sha256"] = "0"*64
    assert_rejected(p, (REQUEST+"\n").encode(), "F4_A9_SOURCE_SNAPSHOT_MISMATCH", from_a9=True)


def test_a9_authority_true_nested(payload):
    p = deepcopy(payload)
    p["programming_context_snapshot"]["handoff_allowed"] = True
    assert_rejected(p, (REQUEST+"\n").encode(), "F4_A9_AUTHORITY_FORBIDDEN", from_a9=True)


def test_a9_upstream_stage_digest_tamper(payload, upstream):
    p = deepcopy(payload)
    p["stage_trace"][0]["output_sha256"] = "0"*64
    with pytest.raises(AdmissionBlocked) as e:
        validate(p, (REQUEST+"\n").encode(), result=upstream)
    assert str(e.value) == "F4_A9_UPSTREAM_STAGE_DIGEST_MISMATCH"


def test_request_line_endings_uses_intake_normalization(payload):
    expected = hashlib.sha256(intake.normalized_request_bytes(
        (REQUEST+"\n").encode())).hexdigest()
    assert payload["request_sha256"] == expected


def test_snapshot_material_paths_from_canonical(payload):
    from analysis.a9.package import _contracts, digest
    parity, schema = _contracts()
    snap = payload["programming_context_snapshot"]
    assert snap["snapshot_schema_digest_sha256"] == digest(schema)
    assert {x["rule_code"] for x in snap["applicable_rules"]} == {
        "SBX-R-USER", "SBX-R-PASS", "SBX-R-LOCK",
        "SBX-R-HASH", "SBX-R-LOG", "SBX-R-ERR"}
    assert snap["applicable_invariants"] == []
    assert snap["currentness_refs"] == []
    assert snap["authority_state"] == "UNKNOWN"
    assert snap["implementation_state"] == "NEW"
    assert snap["material_front_coverage"] == payload["programming_context_snapshot"]["material_front_coverage"]
    assert snap["source_attested"] is False


def test_a9_stage_trace_exact_order(payload):
    assert [s["stage"] for s in payload["stage_trace"]] == [
        "A1","A2","A3","A4","A5","A6","A7","A8","A9"]
    assert all(len(s["output_sha256"]) == 64 for s in payload["stage_trace"])


def test_byte_exact_replay(tmp_path):
    from pilot.orchestrator.intake import canonical
    a = run_f4(tmp_path)
    original = (tmp_path / "pilot/runs/f4-login/analysis.json").read_bytes()
    b = run_f4(tmp_path)
    assert original == (tmp_path / "pilot/runs/f4-login/analysis.json").read_bytes()
    assert original == canonical(a["package"]) == canonical(b["package"])
    assert a["state"] == b["state"]


def test_typed_applicable_rules_and_links(payload):
    rules = payload["applicable_rules"]
    assert rules == payload["programming_context_snapshot"]["applicable_rules"]
    assert len(rules) == 6
    assert not {"SBX-R-PENDING", "SBX-R-CAND"} & {r["rule_code"] for r in rules}
    lock = next(r for r in rules if r["rule_code"] == "SBX-R-LOCK")
    assert lock == {
        "rule_code": "SBX-R-LOCK", "source_ref": "supabase://lf_ops.reglas/3",
        "source_status": "VIGENTE", "source_attested": False,
        "titulo": "Bloquear tras 5 fallos durante 15 minutos",
        "categoria": "rate_limiting",
        "valor_config": {"failed_attempts": 5, "lock_minutes": 15},
        "es_transversal": False, "origen": "DIRECT",
        "front_id": next(f["front_id"] for f in payload["material_fronts"]
                         if f["execution_area"] == "BACKEND"),
        "requirement_id": "REQ-SBX-R-LOCK",
    }
    logged = next(r for r in rules if r["rule_code"] == "SBX-R-LOG")
    assert logged["origen"] == "DERIVED_GLOBAL"
    assert logged["es_transversal"] is True
    assert logged["valor_config"] == {"log_password": False}
    assert {r["requirement_id"] for r in rules} == {
        r["requirement_id"] for r in payload["requirements"]
        if not r.get("derived_from_requirement_id")}
    assert all(r["front_id"] in {f["front_id"] for f in payload["material_fronts"]}
               for r in rules)


def test_numeric_a6_checks_match_typed_source_configs(payload):
    by_code = {r["rule_code"]: r["valor_config"] for r in payload["applicable_rules"]}
    reqs = {r["source_requirement_id"]: r for r in payload["requirements"]}
    # A6 spells the numbers in Spanish, so assert the actual acceptance
    # semantics and raw typed config independently, never derive one from text.
    assert "quinto" in reqs["SBX-R-LOCK"]["acceptance_signal"]
    assert "quince" in reqs["SBX-R-LOCK"]["acceptance_signal"]
    assert "treinta" in reqs["SBX-R-ERR"]["acceptance_signal"]
    assert by_code["SBX-R-LOCK"]["failed_attempts"] == 5
    assert by_code["SBX-R-LOCK"]["lock_minutes"] == 15
    assert by_code["SBX-R-ERR"]["session_minutes"] == 30
    assert type(by_code["SBX-R-LOCK"]["failed_attempts"]) is int
    assert type(by_code["SBX-R-LOCK"]["lock_minutes"]) is int
    assert type(by_code["SBX-R-ERR"]["session_minutes"]) is int
    assert not {"SBX-R-PENDING", "SBX-R-CAND"} & set(by_code)


def test_future_invariants_source_blocks(upstream):
    from analysis.a9.package import _guard_invariants
    a3 = deepcopy(upstream["stages"]["A3"])
    a3["applicable_invariants"] = [{"id": "INV-FUTURE"}]
    with pytest.raises(AdmissionBlocked) as err:
        _guard_invariants(a3)
    assert str(err.value) == "F4_A9_INVARIANTS_SOURCE_UNHANDLED"


def test_typed_rule_parity_tamper_rejected(payload, upstream):
    p = deepcopy(payload)
    p["applicable_rules"][0]["valor_config"] = {"tampered": 999}
    with pytest.raises(AdmissionBlocked) as err:
        validate(p, (REQUEST + "\n").encode(), result=upstream)
    assert str(err.value) == "F4_A9_RULE_PARITY_MISMATCH"
