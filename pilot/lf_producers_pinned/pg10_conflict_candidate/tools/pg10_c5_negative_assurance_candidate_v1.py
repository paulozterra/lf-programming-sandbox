"""PG-10_C5: source-only negative assurance matrix; no verdict or executed tests.

Produces a bound adversarial test plan from PG-10_C1-C4 source candidates.
No fixture supplied by the caller can authenticate itself or claim PASS.
"""
import hashlib
import json
from copy import deepcopy

EXPECTED = {
    "UNILATERAL_REQUIREMENT_REWRITE": ("BLOCKED", "REQUIREMENT_REDEFINITION"),
    "LEGACY_RENAME_WITHOUT_APPROVED_MIGRATION": ("BLOCKED", "UNAPPROVED_LEGACY_RENAME"),
    "UNAUTHENTICATED_MIGRATION_APPROVAL": ("BLOCKED", "MIGRATION_AUTHORITY_UNVERIFIED"),
    "TECHNICAL_DECISION_SENT_TO_HUMAN": ("BLOCKED", "ROUTE_TECHNICAL_TO_PG03"),
    "IMPLEMENTATION_GAP_SENT_AS_QUESTION": ("BLOCKED", "IMPLEMENTATION_IS_NOT_QUESTION"),
    "EVIDENCE_GAP_INVENTED_REQUIREMENT": ("BLOCKED", "QUERY_EXACT_MISSING_EVIDENCE"),
    "REQUIREMENT_GAP_SOLVED_LOCALLY": ("BLOCKED", "RETURN_PHASE1_A3"),
    "DUPLICATE_HUMAN_QUESTION": ("BLOCKED", "CHECK_PRIOR_DECISION"),
    "STALE_PRIOR_DECISION_REUSED": ("BLOCKED", "DECISION_CURRENTNESS_UNVERIFIED"),
    "HUMAN_PACKET_MISSING_OPTIONS_OR_RISK": ("BLOCKED", "INCOMPLETE_DECISION_PACKET"),
    "UNAUTHORIZED_AFFECTED_SCOPE_RESUME": ("BLOCKED", "RESUME_NOT_AUTHORIZED"),
    "UNRELATED_READY_SCOPE_BLOCKED": ("REVIEW_REQUIRED", "SCOPE_ISOLATION_REQUIRED"),
}
SCHEMAS = {
    "pg10_c1": "PG10_C1_CONFLICT_INVENTORY_CANDIDATE_V1",
    "pg10_c2": "PG10_C2_PRECEDENCE_LEGACY_GUARD_CANDIDATE_V1",
    "pg10_c3": "PG10_C3_TYPED_ROUTING_CANDIDATE_V1",
    "pg10_c4": "PG10_C4_HUMAN_DECISION_PACKETS_CANDIDATE_V1",
}
class PG10C5Blocked(ValueError):
    pass

def fail(code):
    raise PG10C5Blocked(code)

def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()

def valid_ref(x):
    return isinstance(x, str) and bool(x.strip())

def frozen(obj, schema, num):
    if not isinstance(obj, dict) or obj.get("schema_version") != schema:
        fail("PG10_C5_SOURCE_SCHEMA_INVALID")
    actual = digest({k: v for k, v in obj.items() if k != "candidate_sha256"})
    if obj.get("candidate_sha256") != actual:
        fail("PG10_C5_SOURCE_DIGEST_INVALID")
    if (obj.get("status") != "CANDIDATE_NOT_ADMITTED"
        or obj.get("production_authority") is not False
        or obj.get("handoff_allowed") is not False
        or obj.get("pg10_c" + num + "_pass") is not False
        or obj.get("pg10_c" + num + "_admitted") is not False):
        fail("PG10_C5_PREMATURE_SOURCE_AUTHORITY")
    return actual

def prepare_pg10_c5(*, pg10_c1, pg10_c2, pg10_c3, pg10_c4, scenario_observations):
    """Accept all 12 declared scenario metadata envelopes, *not executions*.

    Each item: scenario_id, fixture_ref, fixture_sha256, target_conflict_ref,
      expected_result, expected_reason, execution_receipt_ref (always None).
    """
    inputs = {"pg10_c1": pg10_c1, "pg10_c2": pg10_c2,
              "pg10_c3": pg10_c3, "pg10_c4": pg10_c4}
    hashes = {key: frozen(inputs[key], schema, key[-1]) for key, schema in SCHEMAS.items()}
    if (pg10_c2.get("source_pg10_c1_sha256") != hashes["pg10_c1"]
        or pg10_c3.get("source_pg10_c2_sha256") != hashes["pg10_c2"]
        or pg10_c4.get("source_pg10_c3_sha256") != hashes["pg10_c3"]):
        fail("PG10_C5_SOURCE_CHAIN_MISMATCH")
    runs = [obj.get("run_ref") for obj in inputs.values()]
    if len({json.dumps(x, sort_keys=True, default=str) for x in runs}) != 1:
        fail("PG10_C5_RUN_REF_DRIFT")
    universes = []
    for obj in inputs.values():
        solutions = obj.get("solutions")
        if not isinstance(solutions, list) or not solutions:
            fail("PG10_C5_SOLUTION_UNIVERSE_INVALID")
        ids = [s.get("solution_id") for s in solutions if isinstance(s, dict)]
        if len(ids) != len(solutions) or not all(map(valid_ref, ids)) or len(set(ids)) != len(ids):
            fail("PG10_C5_SOLUTION_UNIVERSE_INVALID")
        universes.append(set(ids))
    if not all(s == universes[0] for s in universes):
        fail("PG10_C5_SOLUTION_UNIVERSE_DRIFT")
    if not isinstance(scenario_observations, list) or len(scenario_observations) != len(EXPECTED):
        fail("PG10_C5_SCENARIO_COVERAGE_INVALID")
    rows, seen = [], set()
    for item in scenario_observations:
        fields = {"scenario_id", "fixture_ref", "fixture_sha256", "target_conflict_ref",
                  "expected_result", "expected_reason", "execution_receipt_ref"}
        if not isinstance(item, dict) or set(item) != fields:
            fail("PG10_C5_SCENARIO_SHAPE_INVALID")
        sid = item["scenario_id"]
        if sid not in EXPECTED or sid in seen:
            fail("PG10_C5_SCENARIO_DUPLICATE_OR_UNKNOWN")
        seen.add(sid)
        result, reason = EXPECTED[sid]
        if item["expected_result"] != result or item["expected_reason"] != reason:
            fail("PG10_C5_EXPECTATION_TAMPERED")
        if not valid_ref(item["fixture_ref"]) or not valid_ref(item["target_conflict_ref"]):
            fail("PG10_C5_FIXTURE_REFERENCE_INVALID")
        sha = item["fixture_sha256"]
        if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
            fail("PG10_C5_FIXTURE_DIGEST_SHAPE_INVALID")
        if item["execution_receipt_ref"] is not None:
            fail("PG10_C5_UNVERIFIED_EXECUTION_RECEIPT")
        rows.append({
            "scenario_id": sid,
            "fixture_ref_reported": item["fixture_ref"],
            "fixture_sha256_reported": sha,
            "target_conflict_ref_reported": item["target_conflict_ref"],
            "expected_result": result,
            "expected_reason": reason,
            "executed": False,
            "observed_result": None,
            "observed_reason": None,
            "expectation_satisfied": None,
            "fixture_authenticated": False,
            "worker_stop_verified": False,
            "independent_verdict": None,
        })
    if seen != set(EXPECTED):
        fail("PG10_C5_MISSING_REQUIRED_SCENARIO")
    output = {
        "schema_version": "PG10_C5_NEGATIVE_ASSURANCE_CANDIDATE_V1",
        "status": "CANDIDATE_NOT_ADMITTED",
        "source_candidate_sha256": hashes,
        "scenario_observations_sha256": digest(scenario_observations),
        "run_ref": runs[0], "scenarios": sorted(rows, key=lambda x: x["scenario_id"]),
        "required_case_count": len(EXPECTED), "executed_case_count": 0,
        "real_source_readback_verified": False,
        "fixture_provenance_authenticated": False,
        "decision_ledger_checked": False,
        "worker_blocking_behavior_verified": False,
        "independent_verdict_issued": False,
        "analysis_modified": False, "pg10_c5_pass": False,
        "pg10_c5_admitted": False, "handoff_allowed": False,
        "production_authority": False,
        "next_gate": "EXECUTE_12_ADVERSARIAL_CASES_WITH_AUTHENTIC_RECEIPTS_AND_INDEPENDENT_REVIEW"
    }
    output["candidate_sha256"] = digest(output)
    return deepcopy(output)
