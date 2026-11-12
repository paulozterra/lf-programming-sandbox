"""F2 simulated gate & A6: upstream real F1 stages, no source changes."""
from __future__ import annotations

from copy import deepcopy
import json
import pytest

from analysis.host.run_a1_a6_fixture import run_f2
from analysis.host.simulated_admission_gate import (
    AdmissionBlocked, MODE, admit, digest, seal_envelope, verify,
)
from analysis.a6.implementability import run as a6_run, validate_obligation, _profile_reuse


@pytest.fixture(scope="module")
def valid():
    return run_f2()


def fails(code, fn):
    with pytest.raises(AdmissionBlocked) as err:
        fn()
    assert err.value.code == code


def test_real_login_positive_exact_closed_lift_set(valid):
    assert valid["admission"]["a6_admitted"] is True
    assert valid["admission"]["attestation_mode"] == MODE
    assert valid["admission"]["lifted_codes"] == sorted([
        "SOURCE_READBACK_CURRENTNESS_AND_AUTHORITY_NOT_ATTESTED",
        "A4_EXISTING_SHARED_DEPENDENCIES_NOT_ATTESTED",
        "A2_TYPED_EVIDENCE_CURRENTNESS_OR_SPECIALIST_PENDING",
        "GITHUB_CURRENT_IMPLEMENTATION_AND_AS_IS_MISSING",
    ])
    assert all(flag is False for flag in valid["admission"]["authority_flags"].values())


def test_envelope_missing(valid):
    fails("F2_ADMISSION_ENVELOPE_MISSING",
          lambda: admit(valid["stages"], valid["a2_signals"], None))


def test_tampered_stage_digest(valid):
    packet = deepcopy(valid["stages"])
    packet["A3"]["target_ref"] = "SBX-FORGED"
    fails("F2_STAGE_DIGEST_MISMATCH",
          lambda: admit(packet, valid["a2_signals"], valid["admission_envelope"]))


def test_stage_blocked_rejected(valid):
    packet = deepcopy(valid["stages"])
    packet["A4"]["status"] = "BLOCKED"
    fails("F2_UPSTREAM_BLOCKED:A4",
          lambda: seal_envelope(packet, valid["a2_signals"]))


def test_unknown_code_rejected(valid):
    packet = deepcopy(valid["stages"])
    packet["A3"]["blocking_codes"].append("SBX_OTHER_BLOCKER")
    fails("F2_A3_BLOCKING_SET_INVALID",
          lambda: seal_envelope(packet, valid["a2_signals"]))


def test_specialist_not_lifted(valid):
    signals = deepcopy(valid["a2_signals"])
    signals["depth_signals"]["required_specialist_count"] = 1
    stages = deepcopy(valid["stages"])
    stages["A2"]["classification"]["signals_sha256"] = digest(signals)
    fails("F2_A2_NON_AUTHORITY_UNRESOLVED",
          lambda: seal_envelope(stages, signals))


def test_unknown_materiality_not_lifted(valid):
    signals = deepcopy(valid["a2_signals"])
    signals["depth_signals"]["materiality_level"] = "UNKNOWN"
    stages = deepcopy(valid["stages"])
    stages["A2"]["classification"]["signals_sha256"] = digest(signals)
    fails("F2_A2_NON_AUTHORITY_UNRESOLVED",
          lambda: seal_envelope(stages, signals))


def test_excluded_rule_cannot_be_lifted(valid):
    envelope = deepcopy(valid["admission_envelope"])
    envelope["requested_lifts"].append("SBX-R-PENDING")
    envelope["envelope_sha256"] = digest({
        k: v for k, v in envelope.items() if k != "envelope_sha256"
    })
    fails("F2_LIFT_OUTSIDE_CLOSED_ALLOWLIST",
          lambda: admit(valid["stages"], valid["a2_signals"], envelope))


def test_envelope_digest_tampered(valid):
    envelope = deepcopy(valid["admission_envelope"])
    envelope["envelope_sha256"] = "0" * 64
    fails("F2_ADMISSION_ENVELOPE_DIGEST_INVALID",
          lambda: admit(valid["stages"], valid["a2_signals"], envelope))


def test_unexpected_status_rejected(valid):
    stages = deepcopy(valid["stages"])
    stages["A5"]["status"] = "READY"
    fails("F2_UPSTREAM_STATUS_UNEXPECTED:A5",
          lambda: seal_envelope(stages, valid["a2_signals"]))


def test_new_build_required_for_missing_as_is_lift(valid):
    stages = deepcopy(valid["stages"])
    stages["A4"]["target_change_action"] = "UPDATE"
    fails("F2_NOT_NEW_BUILD", lambda: seal_envelope(stages, valid["a2_signals"]))


def test_six_exact_a6_obligations_unknown_area_and_source_refs(valid):
    rows = valid["a6"]["requirements"]
    assert [x["requirement_id"] for x in rows] == sorted((
        "SBX-R-USER", "SBX-R-PASS", "SBX-R-LOCK",
        "SBX-R-HASH", "SBX-R-LOG", "SBX-R-ERR",
    ))
    a3 = valid["stages"]["A3"]
    assert len(rows) == 6
    assert all(x["area"] == "UNKNOWN" and x["area_evidence_refs"] == [] for x in rows)
    assert all(x["evidence_refs"][0] in a3["source_refs"] for x in rows)
    assert all(x["acceptance_signals"][0] and x["simulation_mode"] == MODE for x in rows)
    assert not {"SBX-R-PENDING", "SBX-R-CAND"} & {
        x["requirement_id"] for x in rows
    }
    assert valid["a6"]["authority_flags"]["production_authority"] is False
    assert valid["a6"]["a9_runtime_validation"] == "DEFERRED_UNTIL_A9"


def test_a6_without_admission(valid):
    fails("F2_ADMISSION_REQUIRED",
          lambda: a6_run(valid["stages"], valid["a2_signals"],
                         valid["admission_envelope"], None))


def test_a6_acceptance_missing(valid):
    item = deepcopy(valid["a6"]["requirements"][0])
    item["acceptance_signals"] = []
    fails("F2_A6_ACCEPTANCE_CRITERION_REQUIRED",
          lambda: validate_obligation(item, _profile_reuse()))


def test_a6_area_invented(valid):
    item = deepcopy(valid["a6"]["requirements"][0])
    item["area"] = "BACKEND"
    fails("F2_A6_AREA_WITHOUT_SOURCE",
          lambda: validate_obligation(item, _profile_reuse()))


def test_a6_how_rejected(valid):
    item = deepcopy(valid["a6"]["requirements"][0])
    item["acceptance_signals"] = ["usar BCrypt 12 rounds en clase X"]
    fails("F2_A6_HOW_FORBIDDEN",
          lambda: validate_obligation(item, _profile_reuse()))


def test_a6_receipt_mutation_fails(valid):
    receipt = deepcopy(valid["admission"])
    receipt["authority_flags"]["production_authority"] = True
    fails("F2_ADMISSION_RECEIPT_DRIFT",
          lambda: a6_run(valid["stages"], valid["a2_signals"],
                         valid["admission_envelope"], receipt))


def test_full_f2_byte_identical():
    from analysis.host.run_a1_a5_fixture import encoded
    assert encoded(run_f2()) == encoded(run_f2())


def test_stage_digests_exact(valid):
    assert verify(valid["stages"], valid["a2_signals"],
                  valid["admission_envelope"], valid["admission"])
    for name, row in valid["stages"].items():
        assert valid["admission"]["stage_sha256"][name] == digest(row)
