"""PG-09_C5 adversarial loop test-matrix intake; never executes or certifies.

The matrix gives test runners explicit mandatory cases. Observations are
self-reported candidate outputs; structural match is NOT a test verdict.
"""
import hashlib
import json
import re

SHA256 = re.compile(r"^[a-f0-9]{64}$")
EXPECTED = {
    "BUDGET_80_WARNING": ("RETURN", "REVIEW_REQUIRED"),
    "BUDGET_100_EXHAUSTED": ("RETURN", "BUDGET_DECISION"),
    "BUDGET_USAGE_UNAVAILABLE": ("RETURN", "BUDGET_DECISION"),
    "WORKER_ATTEMPTS_EXHAUSTED": ("RETURN", "BUDGET_DECISION"),
    "REPEATED_NO_NEW_EVIDENCE": ("BLOCKED", "STAGNATION"),
    "MATERIAL_SCOPE_DRIFT": ("BLOCKED", "MATERIAL_SCOPE_DRIFT"),
    "QUALITY_RULE_DISABLED": ("BLOCKED", "QUALITY_BYPASS"),
    "TEST_REMOVED_TO_PASS": ("BLOCKED", "QUALITY_BYPASS"),
    "SUPPRESSION_WITHOUT_AUTHENTICATED_WAIVER": ("RETURN", "WAIVER_REVIEW"),
}
ADVERSARIAL_NEEDS_INDEPENDENT_PROOF = (
    "BUDGET_80_WARNING",
    "BUDGET_100_EXHAUSTED",
    "BUDGET_USAGE_UNAVAILABLE",
    "WORKER_ATTEMPTS_EXHAUSTED",
    "REPEATED_NO_NEW_EVIDENCE",
    "MATERIAL_SCOPE_DRIFT",
    "QUALITY_RULE_DISABLED",
    "TEST_REMOVED_TO_PASS",
    "SUPPRESSION_WITHOUT_AUTHENTICATED_WAIVER",
)


class PG09C5Blocked(ValueError):
    pass


def fail(reason):
    raise PG09C5Blocked(reason)


def digest(obj):
    return hashlib.sha256(json.dumps(
        obj, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def ref(s):
    return isinstance(s, str) and bool(s.strip())


def check_source(obj, schema):
    if not isinstance(obj, dict) or obj.get("schema_version") != schema:
        fail("PG09_C5_SOURCE_SCHEMA_INVALID")
    sha = obj.get("candidate_sha256")
    if not isinstance(sha, str) or not SHA256.fullmatch(sha) or sha != digest(
        {key: value for key, value in obj.items() if key != "candidate_sha256"}
    ):
        fail("PG09_C5_SOURCE_DIGEST_INVALID")
    if (obj.get("status") != "CANDIDATE_NOT_ADMITTED"
        or obj.get("production_authority") is not False
        or obj.get("handoff_allowed") is not False
        or obj.get("retry_authorized") is not False):
        fail("PG09_C5_SOURCE_AUTHORITY_INVALID")
    return sha


def prepare_pg09_c5(*, scenario_observations):
    """Accept one observed PG09_C4 envelope per mandated adversarial case.

    Each scenario row: scenario_id, fixture_ref, fixture_sha256,
    tool_execution_receipt_ref, observed_pg09_c1, observed_pg09_c4. A genuine runner should
    later bind exact fixture + real recorded execution to authenticated
    tool receipts. This function does not do any of those things.
    """
    if not isinstance(scenario_observations, list) or len(scenario_observations) != len(EXPECTED):
        fail("PG09_C5_ADVERSARIAL_COVERAGE_INCOMPLETE")
    observations = {}
    for row in scenario_observations:
        if not isinstance(row, dict) or set(row) != {
            "scenario_id", "fixture_ref", "fixture_sha256",
            "tool_execution_receipt_ref", "observed_pg09_c1", "observed_pg09_c4"
        }:
            fail("PG09_C5_SCENARIO_SHAPE_INVALID")
        case = row["scenario_id"]
        if (case not in EXPECTED or case in observations
            or not ref(row["fixture_ref"])
            or not isinstance(row["fixture_sha256"], str)
            or not SHA256.fullmatch(row["fixture_sha256"])):
            fail("PG09_C5_SCENARIO_IDENTITY_INVALID")
        if row["tool_execution_receipt_ref"] is not None and not ref(row["tool_execution_receipt_ref"]):
            fail("PG09_C5_EXECUTION_REF_INVALID")
        observations[case] = row
    if set(observations) != set(EXPECTED):
        fail("PG09_C5_MANDATORY_SCENARIOS_MISSING")
    outputs = []
    fixture_refs = set()
    for case in ADVERSARIAL_NEEDS_INDEPENDENT_PROOF:
        row = observations[case]
        if row["fixture_ref"] in fixture_refs:
            fail("PG09_C5_FIXTURE_REF_REUSED")
        fixture_refs.add(row["fixture_ref"])
        c1 = row["observed_pg09_c1"]
        c1_sha = check_source(c1, "PG09_C1_ITERATION_COST_GOVERNOR_CANDIDATE_V1")
        if c1.get("pg09_c1_pass") is not False or c1.get("pg09_c1_admitted") is not False:
            fail("PG09_C5_C1_PREMATURE_VERDICT")
        c4 = row["observed_pg09_c4"]
        c4_sha = check_source(c4, "PG09_C4_TYPED_ESCALATION_CANDIDATE_V1")
        if (c4.get("source_pg09_c1_sha256") != c1_sha or
            c4.get("run_ref") != c1.get("run_ref") or
            c4.get("pg09_c4_pass") is not False
            or c4.get("pg09_c4_admitted") is not False
            or c4.get("escalation_delivered") is not False
            or c4.get("owner_authorization_verified") is not False
            or c4.get("worker_execution_observed") is not False):
            fail("PG09_C5_SOURCE_PREMATURE_VERDICT")
        solutions = c4.get("solutions")
        if (not isinstance(solutions, list) or len(solutions) != 1
            or not isinstance(solutions[0], dict)):
            fail("PG09_C5_SCENARIO_MUST_HAVE_ONE_SOLUTION")
        result = solutions[0]
        expected_type, expected_reason = EXPECTED[case]
        reasons = result.get("reason_codes")
        if (not isinstance(reasons, list) or not reasons
            or any(not ref(x) for x in reasons) or len(set(reasons)) != len(reasons)
            or result.get("escalation_type") not in ("RETURN", "BLOCKED")
            or result.get("retry_authorized") is not False
            or result.get("decision_granted") is not False):
            fail("PG09_C5_TYPED_RESULT_INVALID")
        expected_signal_reported = (
            result["escalation_type"] == expected_type and expected_reason in reasons
        )
        # A generic RETURN does not prove C1 emitted the 80% warning.
        # Bind budget adversarial labels to the matching C1 signal.
        if case == "BUDGET_80_WARNING":
            expected_signal_reported = (expected_signal_reported and
                c1.get("request_diagnostic") == "WARN_80_PERCENT" and
                c1.get("eighty_percent_warning_reported") is True and
                c1.get("requires_decision_reported") is False)
        if case == "BUDGET_100_EXHAUSTED":
            expected_signal_reported = (expected_signal_reported and
                c1.get("request_diagnostic") == "REQUIRES_DECISION" and
                c1.get("requires_decision_reported") is True and
                c1.get("reported_request_known_cost") is not None)
        if case == "BUDGET_USAGE_UNAVAILABLE":
            expected_signal_reported = expected_signal_reported and c1.get("missing_usage_requires_decision") is True
        if case == "WORKER_ATTEMPTS_EXHAUSTED":
            expected_signal_reported = expected_signal_reported and c1.get("iteration_limit_reached_reported") is True
        outputs.append({
            "scenario_id": case,
            "fixture_ref_reported": row["fixture_ref"],
            "fixture_sha256_reported": row["fixture_sha256"],
            "source_pg09_c1_sha256": c1_sha,
            "source_pg09_c4_sha256": c4_sha,
            "tool_execution_receipt_ref_reported": row["tool_execution_receipt_ref"],
            "expected_type": expected_type,
            "expected_reason": expected_reason,
            "reported_type": result["escalation_type"],
            "reported_reason_codes": sorted(reasons),
            "structural_expectation_matched_unverified": expected_signal_reported,
            "fixture_authenticity_verified": False,
            "tool_execution_authenticated": False,
            "actual_scenario_executed": False,
            "runtime_retry_prevention_verified": False,
            "independent_verdict": "NOT_ISSUED",
        })
    output = {
        "schema_version": "PG09_C5_ADVERSARIAL_ASSURANCE_CANDIDATE_V1",
        "status": "CANDIDATE_NOT_ADMITTED",
        "scenario_matrix_version": "PG09_C5_REQUIRED_ADVERSARIAL_MATRIX_V1",
        "scenario_observations_sha256": digest(scenario_observations),
        "required_case_count": len(EXPECTED),
        "cases": outputs,
        "reported_structure_matches_all_expectations": all(
            row["structural_expectation_matched_unverified"] for row in outputs
        ),
        "executed_test_count": 0,
        "adversarial_cases_executed": False,
        "test_runner_attested": False,
        "fixture_provenance_authenticated": False,
        "worker_blocking_behavior_verified": False,
        "independent_verdict_issued": False,
        "pg09_c5_pass": False,
        "pg09_c5_admitted": False,
        "handoff_allowed": False,
        "retry_authorized": False,
        "production_authority": False,
        "next_gate": "REAL_ADVERSARIAL_HARNESS_EXACT_FIXTURE_EXECUTION_AND_INDEPENDENT_VERDICT",
    }
    output["candidate_sha256"] = digest(output)
    return output
