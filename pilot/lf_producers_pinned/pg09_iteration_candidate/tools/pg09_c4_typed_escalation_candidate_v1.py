"""PG-09_C4: typed escalation projection. No real routing, retry or authority."""
import hashlib
import json
import re

SHA = re.compile(r"^[a-f0-9]{64}$")

class PG09C4Blocked(ValueError):
    pass

def fail(reason):
    raise PG09C4Blocked(reason)

def digest(x):
    return hashlib.sha256(json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()

def ref(x):
    return isinstance(x, str) and bool(x.strip())

def source(obj, schema):
    if not isinstance(obj, dict) or obj.get("schema_version") != schema:
        fail("PG09_C4_SOURCE_SCHEMA_INVALID")
    sha = obj.get("candidate_sha256")
    if not isinstance(sha, str) or not SHA.fullmatch(sha) or sha != digest(
        {k: v for k, v in obj.items() if k != "candidate_sha256"}
    ):
        fail("PG09_C4_SOURCE_DIGEST_INVALID")
    if (obj.get("status") != "CANDIDATE_NOT_ADMITTED" or
        obj.get("production_authority") is not False or
        obj.get("handoff_allowed") is not False):
        fail("PG09_C4_SOURCE_AUTHORITY_INVALID")
    return sha

def index(rows):
    if not isinstance(rows, list) or not rows:
        fail("PG09_C4_SOLUTIONS_MISSING")
    out = {}
    for row in rows:
        if not isinstance(row, dict) or not ref(row.get("solution_id")) or row["solution_id"] in out:
            fail("PG09_C4_SOLUTION_IDS_INVALID")
        out[row["solution_id"]] = row
    return out

def prepare_pg09_c4(*, pg09_c1, pg09_c2, pg09_c3, escalation_context):
    """Project typed RETURN/BLOCKED with diagnostics, never dispatch."""
    s1 = source(pg09_c1, "PG09_C1_ITERATION_COST_GOVERNOR_CANDIDATE_V1")
    s2 = source(pg09_c2, "PG09_C2_CONVERGENCE_GUARD_CANDIDATE_V1")
    s3 = source(pg09_c3, "PG09_C3_QUALITY_BYPASS_GUARD_CANDIDATE_V1")
    if (pg09_c2.get("source_pg09_c1_sha256") != s1 or
        pg09_c3.get("source_pg09_c2_sha256") != s2 or
        any(obj.get("retry_authorized") is not False for obj in (pg09_c1, pg09_c2, pg09_c3)) or
        any(obj.get("pg09_c" + str(i) + "_pass") is not False or
            obj.get("pg09_c" + str(i) + "_admitted") is not False
            for i, obj in enumerate((pg09_c1, pg09_c2, pg09_c3), 1))):
        fail("PG09_C4_CHAIN_OR_AUTHORITY_INVALID")
    c1, c2, c3, ctx = (index(pg09_c1.get("solutions")), index(pg09_c2.get("solutions")),
                       index(pg09_c3.get("solutions")), index(escalation_context))
    if set(c1) != set(c2) or set(c1) != set(c3) or set(c1) != set(ctx):
        fail("PG09_C4_COVERAGE_DRIFT")
    results = []
    for sid in sorted(c1):
        row = ctx[sid]
        if set(row) != {"solution_id", "run_ref", "owner_decision_ref", "diagnostic_evidence_refs"}:
            fail("PG09_C4_CONTEXT_SHAPE_INVALID")
        if row["run_ref"] != pg09_c1.get("run_ref") or not ref(row["owner_decision_ref"]):
            fail("PG09_C4_RUN_OR_OWNER_INVALID")
        refs = row["diagnostic_evidence_refs"]
        if not isinstance(refs, list) or not refs or any(not ref(x) for x in refs) or len(set(refs)) != len(refs):
            fail("PG09_C4_DIAGNOSTIC_REFERENCES_INVALID")
        budget, conv, quality = c1[sid], c2[sid], c3[sid]
        reasons = []
        if quality.get("diagnostic") == "BLOCK":
            reasons.append("QUALITY_BYPASS")
        if conv.get("diagnostic") == "STOP_AND_RECLASSIFY" or any(
            it.get("diagnostic") == "STOP_AND_RECLASSIFY" for it in conv.get("iterations", [])
        ):
            reasons.append("STAGNATION")
        if conv.get("diagnostic") == "BLOCK_ROUTE_PG10" or any(
            it.get("diagnostic") == "BLOCK_ROUTE_PG10" for it in conv.get("iterations", [])
        ):
            reasons.append("MATERIAL_SCOPE_DRIFT")
        if (pg09_c1.get("requires_decision_reported") is True or
            budget.get("cost_unknown") is True or budget.get("attempt_limit_reached") is True):
            reasons.append("BUDGET_DECISION")
        if quality.get("diagnostic") == "REQUIRES_WAIVER_VERIFICATION" or any(
            it.get("diagnostic") == "REQUIRES_WAIVER_VERIFICATION"
            for it in quality.get("iterations", [])
        ):
            reasons.append("WAIVER_REVIEW")
        if not reasons:
            reasons.append("REVIEW_REQUIRED")
        reasons = sorted(set(reasons))
        escalation_type = ("BLOCKED" if set(reasons).intersection(
            {"QUALITY_BYPASS", "STAGNATION", "MATERIAL_SCOPE_DRIFT"}) else "RETURN")
        results.append({
            "solution_id": sid, "run_ref": row["run_ref"],
            "escalation_type": escalation_type, "reason_codes": reasons,
            "owner_decision_ref_reported": row["owner_decision_ref"],
            "diagnostic_evidence_refs_reported": sorted(refs),
            "source_convergence_diagnostic": conv.get("diagnostic"),
            "source_quality_diagnostic": quality.get("diagnostic"),
            "source_cost_unknown": budget.get("cost_unknown"),
            "escalation_delivered": False,
            "decision_granted": False, "retry_authorized": False,
            "worker_execution_observed": False, "evidence_authenticated": False
        })
    result = {
        "schema_version": "PG09_C4_TYPED_ESCALATION_CANDIDATE_V1",
        "status": "CANDIDATE_NOT_ADMITTED",
        "source_pg09_c1_sha256": s1, "source_pg09_c2_sha256": s2,
        "source_pg09_c3_sha256": s3, "escalation_context_sha256": digest(escalation_context),
        "run_ref": pg09_c1.get("run_ref"), "solutions": results,
        "any_blocked_reported": any(x["escalation_type"] == "BLOCKED" for x in results),
        "escalation_delivered": False, "owner_authorization_verified": False,
        "evidence_authenticated": False, "worker_execution_observed": False,
        "retry_authorized": False, "pg09_c4_pass": False,
        "pg09_c4_admitted": False, "handoff_allowed": False,
        "production_authority": False,
        "next_gate": "RUNTIME_ROUTING_TYPED_ESCALATION_RECEIPT_AND_NEGATIVE_TESTS"
    }
    result["candidate_sha256"] = digest(result)
    return result
