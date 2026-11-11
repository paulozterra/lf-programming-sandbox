"""H2-C4 boundary: PG-02 classification is not a PG-03 current-run receipt.

This is a source-only negative contract test, not an authenticated handoff.
"""
import copy
from test_pg02_classifier_v1 import s, m, pg01_binding
from pg02_classification_outcome_v1 import classify_with_outcome

result = classify_with_outcome(copy.deepcopy(s), copy.deepcopy(m), pg01_binding=copy.deepcopy(pg01_binding))
assert result["decision"] == "CANDIDATE_ONLY"
assert result["status"] == "CANDIDATE_NOT_ADMITTED"
assert result["dispatch_allowed"] is False
assert result["candidate"]["status"] == "CANDIDATE_NOT_ADMITTED"
# No canonical execution/run identity or authenticated receipt can be inferred
# from a synthetic PG-01_C4 binding or candidate classifier output.
for forbidden in ("execution_id", "run_id", "verified_receipt", "current_receipts",
                  "pg03_dispatch_receipt", "production_authority"):
    assert forbidden not in result
    assert forbidden not in result["candidate"]

tampered = copy.deepcopy(s)
tampered["scope_front_matrix"][0]["front_status"] = "OPTIONAL"
negative = classify_with_outcome(tampered, copy.deepcopy(m), pg01_binding=copy.deepcopy(pg01_binding))
assert negative["decision"] == "CONTRADICTION"
assert negative["return_to"] == "ANALYSIS_PHASE_1"
assert negative["dispatch_allowed"] is False
assert "candidate" not in negative
print("PG02_H2C4_HANDOFF_BOUNDARY_PASS candidate_no_receipt=1 contradiction_no_dispatch=1")
