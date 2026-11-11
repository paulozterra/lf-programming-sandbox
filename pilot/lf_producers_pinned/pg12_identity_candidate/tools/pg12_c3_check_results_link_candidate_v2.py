"""PG-12_C3: PG-08/PG-11 check-result links bound to candidate identity.

Links are caller declarations, not verified execution receipts or PASS results.
No source-only artifact can promote a checkpoint or enable a handoff.
"""
import hashlib
import json
import re
from copy import deepcopy

C2_SCHEMA = "PG12_C2_EXECUTION_INPUTS_USAGE_CANDIDATE_V2"
CHECKS = tuple([f"PG-08_C{i}" for i in range(1, 9)] +
               [f"PG-11_C{i}" for i in range(1, 6)])
SHA = re.compile(r"^[a-f0-9]{64}$")
OUTCOMES = {"PASS", "FAIL", "BLOCKED", "NOT_RUN", "INCONCLUSIVE"}

class PG12C3Blocked(ValueError):
    pass

def fail(reason):
    raise PG12C3Blocked(reason)

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode()).hexdigest()

def ref(value):
    return isinstance(value, str) and bool(value.strip()) and value == value.strip()

def prepare_pg12_c3(*, pg12_c2, candidate_identity_sha256, check_observations):
    """Bind declared check outcomes to a candidate and stage.

    Each observation:
      checkpoint_code, candidate_identity_sha256, check_contract_ref,
      result_ref, result_digest_sha256, runner_ref, observed_outcome,
      execution_receipt_ref.

    A missing receipt is allowed only when observed_outcome=NOT_RUN.
    A nonempty receipt is a *claim*, never evidence of authenticity.
    """
    if not isinstance(pg12_c2, dict) or pg12_c2.get("schema_version") != C2_SCHEMA:
        fail("PG12_C3_SOURCE_SCHEMA_INVALID")
    upstream = digest({k: v for k, v in pg12_c2.items() if k != "candidate_sha256"})
    if upstream != pg12_c2.get("candidate_sha256"):
        fail("PG12_C3_SOURCE_DIGEST_INVALID")
    if (pg12_c2.get("status") != "CANDIDATE_NOT_ADMITTED" or
        pg12_c2.get("pg12_c2_pass") is not False or
        pg12_c2.get("pg12_c2_admitted") is not False or
        pg12_c2.get("handoff_allowed") is not False or
        pg12_c2.get("production_authority") is not False or
        pg12_c2.get("real_run_receipt_verified") is not False):
        fail("PG12_C3_PREMATURE_AUTHORITY")
    if not isinstance(candidate_identity_sha256, str) or not SHA.fullmatch(candidate_identity_sha256):
        fail("PG12_C3_IDENTITY_DIGEST_INVALID")
    if pg12_c2.get("source_pg12_c1_sha256") != candidate_identity_sha256:
        fail("PG12_C3_IDENTITY_CHAIN_DRIFT")
    if not isinstance(check_observations, list) or len(check_observations) != len(CHECKS):
        fail("PG12_C3_CHECK_COVERAGE_INVALID")
    seen, rows = set(), []
    for item in check_observations:
        fields = {"checkpoint_code", "candidate_identity_sha256",
                  "check_contract_ref", "result_ref", "result_digest_sha256",
                  "runner_ref", "observed_outcome", "execution_receipt_ref"}
        if not isinstance(item, dict) or set(item) != fields:
            fail("PG12_C3_CHECK_SHAPE_INVALID")
        chk = item["checkpoint_code"]
        if chk not in CHECKS or chk in seen:
            fail("PG12_C3_UNKNOWN_OR_DUPLICATE_CHECK")
        seen.add(chk)
        if item["candidate_identity_sha256"] != candidate_identity_sha256:
            fail("PG12_C3_CANDIDATE_IDENTITY_MISMATCH")
        outcome = item["observed_outcome"]
        if outcome not in OUTCOMES:
            fail("PG12_C3_OUTCOME_INVALID")
        if not ref(item["check_contract_ref"]) or not ref(item["runner_ref"]):
            fail("PG12_C3_CHECK_PROVENANCE_REF_INVALID")
        receipt = item["execution_receipt_ref"]
        result_ref, result_sha = item["result_ref"], item["result_digest_sha256"]
        if outcome == "NOT_RUN":
            if receipt is not None or result_ref is not None or result_sha is not None:
                fail("PG12_C3_UNRUN_CHECK_HAS_RECEIPT")
        else:
            if (not ref(receipt) or not ref(result_ref) or
                not isinstance(result_sha, str) or not SHA.fullmatch(result_sha)):
                fail("PG12_C3_EXECUTED_RESULT_CLAIM_INCOMPLETE")
        rows.append({
            "checkpoint_code": chk,
            "candidate_identity_sha256": candidate_identity_sha256,
            "check_contract_ref_reported": item["check_contract_ref"],
            "runner_ref_reported": item["runner_ref"],
            "result_ref_reported": result_ref,
            "result_digest_sha256_reported": result_sha,
            "execution_receipt_ref_reported": receipt,
            "observed_outcome_reported": outcome,
            "result_verified": False,
            "receipt_authenticated": False,
            "runner_authenticated": False,
            "same_candidate_execution_verified": False,
            "check_pass_qualified": False
        })
    if seen != set(CHECKS):
        fail("PG12_C3_REQUIRED_CHECKS_MISSING")
    result = {
        "schema_version": "PG12_C3_CHECK_RESULTS_LINK_CANDIDATE_V2",
        "status": "CANDIDATE_NOT_ADMITTED",
        "source_pg12_c2_sha256": upstream,
        "source_pg12_c1_sha256": candidate_identity_sha256,
        "linked_check_count": len(rows),
        "check_observations_sha256": digest(check_observations),
        "check_results": sorted(rows, key=lambda x: x["checkpoint_code"]),
        "real_checks_executed_by_this_component": 0,
        "verified_check_pass_count": 0,
        "all_check_results_verified": False,
        "candidate_binding_verified": False,
        "review_receipts_authenticated": False,
        "pg12_c3_pass": False, "pg12_c3_admitted": False,
        "handoff_allowed": False, "production_authority": False,
        "next_gate": "READBACK_PG08_PG11_REAL_CHECK_RECEIPTS_AND_CANDIDATE_IDENTITY"
    }
    result["candidate_sha256"] = digest(result)
    return deepcopy(result)
