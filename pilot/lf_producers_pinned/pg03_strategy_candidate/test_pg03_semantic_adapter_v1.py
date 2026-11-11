"""Invoke LF existing deterministic semantic-result validator; no model call."""
from pathlib import Path
from pg03_semantic_adapter_v1 import verify_semantic_candidate
root=Path(__file__).resolve().parents[4]
validator=root/"profiles/systemic_root_cause_repair_lf/validators/validate_semantic_judge_result.py"
# This validator is profile-specific: verify only result shape, not a PG-03 semantic verdict.
assert validator.is_file(),validator
sha="a"*64
result={"verdict":"PASS_INDEPENDENT_SEMANTIC","candidate_sha256":sha,"scope_packet_sha256":sha,
        "observed_candidate_changes":[],"requirement_reconciliation":[],
        "change_declaration_reconciliation":[],"scope_conformance_reconciliation":[],
        "invariant_results":[],"blocking_codes":[],"open_design_decisions_found":False}
out=verify_semantic_candidate(result=result,scope_packet={},candidate_sha256=sha,scope_sha256=sha,validator_path=validator)
assert out["code"]=="EXISTING_SEMANTIC_VALIDATOR_REJECTED",out
assert "INVARIANT_COVERAGE_INCOMPLETE" in out["details"]
assert out["production_authority"] is False
mismatch=verify_semantic_candidate(result=result,scope_packet={},candidate_sha256="b"*64,scope_sha256=sha,validator_path=validator)
assert "SEMANTIC_JUDGE_CANDIDATE_SHA_MISMATCH" in mismatch["details"]
print("PG03_EXISTING_SEMANTIC_VALIDATOR_NEGATIVE_PASS incomplete=1 mismatch=1 authority=0")
