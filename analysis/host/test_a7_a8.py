"""F3: real F1/F2 chain → A7/A8; negative guards, byte determinism."""
from copy import deepcopy

import pytest

from analysis.host.run_a1_a8_fixture import run_f3
from analysis.host.run_a1_a5_fixture import encoded
from analysis.a7.front_coverage import run as a7_run, validate_coverage, _material_candidates
from analysis.a8.stop_rule import run as a8_run
from analysis.host.simulated_admission_gate import AdmissionBlocked, digest


@pytest.fixture(scope="module")
def case():
    return run_f3()


def rejects(code, fn):
    with pytest.raises(AdmissionBlocked) as err:
        fn()
    assert err.value.code == code


def reseal(packet, field):
    packet[field] = digest({k:v for k,v in packet.items() if k != field})
    return packet


def test_login_all_six_obligations_have_required_front(case):
    fronts = case["a7"]["material_fronts"]
    bound = [code for row in fronts if row["status"] == "REQUIRED"
             for code in row["obligation_refs"]]
    expected = {x["requirement_id"] for x in case["a6"]["requirements"]}
    assert len(bound) == 6
    assert set(bound) == expected
    assert case["a7"]["all_material_fronts_accounted"] is True
    assert not case["a7"]["unmapped_material_signals"]
    assert set(case["a7"]["front_candidate_refs"]) == {f["candidate_ref"] for f in fronts}


def test_login_decision_preserves_real_a4_unknown(case):
    # F2 A4 always leaves shared dependencies not attested. A8 cannot
    # artificially STOP even when coverage accounting is complete.
    a7, a8 = case["a7"], case["a8"]
    assert a8["decision"] == "CONTINUE", a8
    assert "A4:A4_EXISTING_SHARED_DEPENDENCIES_NOT_ATTESTED" in a8["requested_material_evidence_refs"]
    assert a8["decision_stable"] is False
    assert a7["all_material_fronts_accounted"] is True
    lifted = [f for f in a7["material_fronts"] if f["closure_basis"] == "SIMULATED_ADMISSION_LIFT"]
    assert len(lifted) == 1
    assert lifted[0]["closure"] == "CLOSED"
    assert lifted[0]["lifted_code"] == "A4_EXISTING_SHARED_DEPENDENCIES_NOT_ATTESTED"
    assert all(f["closure"] != "BLOCKED" for f in a7["material_fronts"])
    assert a8["additional_available_evidence_capable_of_changing_material_decision"] == []


def test_no_admission(case):
    rejects("F2_ADMISSION_REQUIRED", lambda: a7_run(
        case["stages"], case["a2_signals"], case["admission_envelope"],
        None, case["a6"], case["category_sources"]))


def test_stage_digest_tampered(case):
    stages = deepcopy(case["stages"])
    stages["A3"]["target_ref"] = "SBX-FORGERY"
    rejects("F2_STAGE_DIGEST_MISMATCH", lambda: a7_run(
        stages, case["a2_signals"], case["admission_envelope"],
        case["admission"], case["a6"], case["category_sources"]))


def test_a6_fingerprint_tampered(case):
    a6 = deepcopy(case["a6"])
    a6["requirements"][0]["outcome"] = "FORGED"
    rejects("F3_A7_A6_DIGEST_OR_ADMISSION_INVALID", lambda: a7_run(
        case["stages"], case["a2_signals"], case["admission_envelope"],
        case["admission"], a6, case["category_sources"]))


def test_candidate_front_omission_rejected(case):
    a7 = deepcopy(case["a7"])
    a7["material_fronts"].pop()
    rejects("F3_A7_SILENT_OMISSION_OR_DUPLICATE", lambda: validate_coverage(
        a7, case["stages"]["A3"], case["stages"]["A4"], case["a6"], case["admission"], case["category_sources"]))


def test_a6_obligation_without_front_rejected(case):
    a7 = deepcopy(case["a7"])
    a7["material_fronts"] = [x for x in a7["material_fronts"]
                              if "SBX-R-LOG" not in x["obligation_refs"]]
    rejects("F3_A7_SILENT_OMISSION_OR_DUPLICATE", lambda: validate_coverage(
        a7, case["stages"]["A3"], case["stages"]["A4"], case["a6"], case["admission"], case["category_sources"]))


def test_unknown_material_signal_requires_blocked_front(case):
    a3 = deepcopy(case["stages"]["A3"])
    item = a3["material_contract_readback"]["status_items"][0]
    item["source_status"] = "UNKNOWN"
    fronts = _material_candidates(a3, case["stages"]["A4"], case["a6"], case["admission"], case["category_sources"])
    assert fronts[item["source_ref"]]["closure"] == "BLOCKED"
    assert fronts[item["source_ref"]]["blockers"]


def test_free_text_never_assigns_execution_area(case):
    a7 = deepcopy(case["a7"])
    a7["material_fronts"][0]["execution_area_hint"] = "BACKEND"
    rejects("F3_A7_FRONT_DERIVATION_DRIFT:" +
            a7["material_fronts"][0]["candidate_ref"],
            lambda: validate_coverage(a7, case["stages"]["A3"],
                                     case["stages"]["A4"], case["a6"], case["admission"], case["category_sources"]))


def test_multi_area_type_does_not_invent_area(case):
    fronts = case["a7"]["material_fronts"]
    state = [x for x in fronts if x["front_kind"] == "STATE_ERROR"]
    assert state
    assert all(x["execution_area_hint"] == "UNKNOWN"
               and x["execution_area_candidates"] == ["BACKEND", "FRONTEND"]
               and x["execution_area_policy"] == "SANDBOX_HINT" for x in state)


def test_area_table_cannot_be_inferred_from_outcome(case):
    a7 = deepcopy(case["a7"])
    row = next(x for x in a7["material_fronts"] if x["front_kind"] == "OTHER")
    row["reason"] = "BACKEND endpoint required according to free text"
    row["execution_area_hint"] = "BACKEND"
    rejects("F3_A7_FRONT_DERIVATION_DRIFT:" + row["candidate_ref"],
            lambda: validate_coverage(a7, case["stages"]["A3"],
                                     case["stages"]["A4"], case["a6"], case["admission"], case["category_sources"]))


def test_a8_blocked_front_never_stops(case):
    a7 = deepcopy(case["a7"])
    row = next(f for f in a7["material_fronts"] if f["closure_basis"] == "SIMULATED_ADMISSION_LIFT")
    row["closure"] = "BLOCKED"
    row["closure_basis"] = "MATERIAL_GAP_UNRESOLVED"
    row["blockers"] = ["F3_NEW_UNLIFTED_MATERIAL_GAP"]
    row["lifted_code"] = None
    row["admission_evidence_ref"] = None
    a7["coverage_fingerprint_sha256"] = digest({k:v for k,v in a7.items() if k != "coverage_fingerprint_sha256"})
    check = a8_run(case["stages"]["A3"], case["stages"]["A5"], a7)
    assert check["decision"] != "STOP"
    assert "F3_NEW_UNLIFTED_MATERIAL_GAP" in check["requested_material_evidence_refs"]


def test_a8_owner_question_requires_decision(case):
    a5 = deepcopy(case["stages"]["A5"])
    a5["status"] = "REQUIRES_DECISION"
    a5["unresolved_material_questions"] = ["Owner must approve security trade-off"]
    a8 = a8_run(case["stages"]["A3"], a5, case["a7"])
    assert a8["decision"] == "REQUIRES_DECISION"
    assert a8["unresolved_decision_changing_questions"] == [
        "Owner must approve security trade-off"]


def test_a8_exact_missing_material_evidence_continues(case):
    a8 = a8_run(case["stages"]["A3"], case["stages"]["A5"], case["a7"])
    assert a8["decision"] == "CONTINUE"
    assert a8["requested_material_evidence_refs"] == [
        "A4:A4_EXISTING_SHARED_DEPENDENCIES_NOT_ATTESTED"]
    assert a8["continuation_policy"] == {
        "continue_only_for_material_evidence": True,
        "no_curiosity_search": True,
        "no_duplicate_read": True,
        "no_full_scan_without_material_trigger": True,
    }


def test_a8_invalid_input_blocked(case):
    a8 = a8_run(None, case["stages"]["A5"], case["a7"])
    assert a8["decision"] == "BLOCKED"
    assert a8["blocking_code"] == "F3_A8_INPUT_INVALID"


def test_a8_mismatched_coverage_fingerprint_blocked(case):
    a7 = deepcopy(case["a7"])
    a7["material_fronts"][0]["status"] = "REUSE_AS_IS"
    a8 = a8_run(case["stages"]["A3"], case["stages"]["A5"], a7)
    assert a8["decision"] == "BLOCKED"
    assert a8["blocking_code"] == "F3_A8_COVERAGE_DIGEST_INVALID"


def test_status_and_area_values_are_contract_bounded(case):
    fronts = case["a7"]["material_fronts"]
    assert all(x["status"] in ("REQUIRED", "REUSE_AS_IS", "NOT_APPLICABLE")
               and x["closure"] in ("CLOSED", "BLOCKED")
               and x["front_kind"]
               and x["execution_area_hint"] in
               ("BACKEND", "FRONTEND", "DATA", "UNKNOWN") for x in fronts)


def test_f3_inherits_security_and_sandbox_boundary(case):
    assert case["a7"]["simulation_mode"] == "SIMULATED_SANDBOX_ONLY"
    assert case["a8"]["simulation_mode"] == "SIMULATED_SANDBOX_ONLY"
    assert case["a7"]["materiality_level"] == case["a8"]["materiality_level"] == "HIGH"
    assert case["a7"]["requires_independent_exam"] is True
    assert case["a8"]["requires_independent_exam"] is True
    assert case["a7"]["authority_flags"]["production_authority"] is False


def test_f3_byte_exact_determinism():
    assert encoded(run_f3()) == encoded(run_f3())


def test_a7_variable_number_of_obligations_accepted(case):
    subset = deepcopy(case["a6"])
    subset["requirements"] = subset["requirements"][:-1]
    fronts = _material_candidates(case["stages"]["A3"], case["stages"]["A4"],
                                  subset, case["admission"], case["category_sources"])
    linked = {c for row in fronts.values() for c in row["obligation_refs"]}
    assert len(linked) == 5
    assert linked == {r["requirement_id"] for r in subset["requirements"]}


def test_a7_empty_obligation_list_blocked(case):
    empty = deepcopy(case["a6"])
    empty["requirements"] = []
    rejects("F3_A7_A6_OBLIGATIONS_INVALID", lambda: _material_candidates(
        case["stages"]["A3"], case["stages"]["A4"], empty,
        case["admission"], case["category_sources"]))


def test_a7_category_normalization_unknown_fallback():
    from analysis.a7.front_coverage import category_kind
    assert category_kind("SECURITY") == category_kind("seguridad") == "SECURITY_PRIVACY"
    assert category_kind("rate_limiting") == "SECURITY_PRIVACY"
    assert category_kind("UX") == category_kind("copy") == "UI_VISUAL"
    assert category_kind("error_states") == "STATE_ERROR"
    assert category_kind("datos") == "DATA_CONTRACT"
    assert category_kind("api") == "API_CONTRACT"
    assert category_kind("analytics") == "ANALYTICS"
    assert category_kind("FLUJO") == "OTHER"
    assert category_kind("unmapped-category") == "OTHER"


def test_a7_category_comes_from_sha_pinned_host_not_free_text(case):
    rows = case["a7"]["material_fronts"]
    by_obligation = {code: row for row in rows for code in row["obligation_refs"]}
    assert by_obligation["SBX-R-LOCK"]["front_kind"] == "SECURITY_PRIVACY"
    assert by_obligation["SBX-R-HASH"]["front_kind"] == "SECURITY_PRIVACY"
    assert by_obligation["SBX-R-LOG"]["front_kind"] == "SECURITY_PRIVACY"
    assert by_obligation["SBX-R-ERR"]["front_kind"] == "STATE_ERROR"
    assert by_obligation["SBX-R-USER"]["front_kind"] == "OTHER"
    assert by_obligation["SBX-R-PASS"]["front_kind"] == "OTHER"
    assert all(x["execution_area_policy"] == "SANDBOX_HINT" for x in rows)
    assert case["category_sources"]["fixture_provenance"]["direct_rules.json"].startswith(
        "fixture://sbx_auth_login/direct_rules.json@")


def test_a7_only_admitted_code_lifted(case):
    rows = case["a7"]["material_fronts"]
    lifted = [x for x in rows if x["closure_basis"] == "SIMULATED_ADMISSION_LIFT"]
    assert len(lifted) == 1
    assert lifted[0]["lifted_code"] in case["admission"]["lifted_codes"]
    assert lifted[0]["admission_evidence_ref"] == "sha256:" + digest(case["admission"])
    assert lifted[0]["admission_evidence_ref"] in lifted[0]["evidence_refs"]


def test_a7_nonlifted_material_gap_remains_blocked(case):
    a4 = deepcopy(case["stages"]["A4"])
    a4["unresolved_material_impacts"].append({
        "code": "F3_NEW_UNLIFTED_MATERIAL_GAP",
        "source_id": "S3_OTHER",
    })
    fronts = _material_candidates(case["stages"]["A3"], a4, case["a6"],
                                  case["admission"], case["category_sources"])
    blocked = [x for x in fronts.values() if "F3_NEW_UNLIFTED_MATERIAL_GAP" in x["blockers"]]
    assert len(blocked) == 1
    assert blocked[0]["closure"] == "BLOCKED"
    assert blocked[0]["closure_basis"] == "MATERIAL_GAP_UNRESOLVED"
