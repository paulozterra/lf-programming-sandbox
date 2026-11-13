"""T1-A source-only bindings: do not infer implementation area from A7 hints."""
from analysis.a9.front_bindings import bind


REQ = [
    {"requirement_id": "REQ-SBX-R-USER", "source_requirement_id": "SBX-R-USER",
     "evidence_refs": ["supabase://lf_ops.reglas/1"]},
    {"requirement_id": "REQ-SBX-R-ERR", "source_requirement_id": "SBX-R-ERR",
     "evidence_refs": ["supabase://lf_ops.reglas/5"]},
]
SECTIONS = {
    "fields": [{"field_code": "SBX-F-USER", "status": "VIGENTE", "required": True}],
    "errors": [{"error_code": "SBX-E-GENERIC", "status": "VIGENTE", "generic": True}],
}
RULES = {"SBX-R-ERR": {"config": {"generic_error": True}}}


def front(candidate, kind, evidence):
    return {"front_id": "F3-test", "candidate_ref": candidate, "front_kind": kind,
            "evidence_refs": evidence, "obligation_mode": "REQUIRED",
            "blockers": [], "closure": "CLOSED", "reason": "Source readback"}


def test_rule_source_binds_exact_requirement():
    row = bind(front("supabase://lf_ops.reglas/1", "API_CONTRACT",
                     ["supabase://lf_ops.reglas/1"]), REQ, SECTIONS, RULES)
    assert row["requirement_ids"] == ["REQ-SBX-R-USER"]
    assert row["execution_area"] == "BACKEND"
    assert row["execution_area_source_ref"] == "supabase://lf_ops.reglas/1"
    assert row["closure"] == "CLOSED"


def test_typed_field_binds_matching_rule_but_not_other_area():
    path = "supabase://lf_ops.pantallas/SBX-AUTH-LOGIN#contract/fields/0"
    row = bind(front(path, "DATA_CONTRACT", [path]), REQ, SECTIONS, RULES)
    assert row["requirement_ids"] == ["REQ-SBX-R-USER"]
    assert row["execution_area"] == "DATA"
    assert row["execution_area_source_ref"] == path


def test_generic_screen_error_is_not_implicitly_single_area():
    path = "supabase://lf_ops.pantallas/SBX-AUTH-LOGIN#contract/errors/0"
    row = bind(front(path, "STATE_ERROR", [path]), REQ, SECTIONS, RULES)
    assert row["requirement_ids"] == ["REQ-SBX-R-ERR"]
    assert row["execution_area"] is None
    assert row["closure"] == "BLOCKED"


def test_unrelated_screen_metadata_and_a4_gap_never_ready():
    for candidate in ("supabase://lf_ops.pantallas/SBX-AUTH-LOGIN#contract/metadata",
                      "A4:unresolved:A4_EXISTING_SHARED_DEPENDENCIES_NOT_ATTESTED:S3_INV_OBJECT"):
        row = bind(front(candidate, "OTHER", []), REQ, SECTIONS, RULES)
        assert not row["requirement_ids"]
        assert "A9_REQUIRED_FRONT_WITHOUT_REQUIREMENT" in row["blockers"]
        assert row["closure"] == "BLOCKED"
