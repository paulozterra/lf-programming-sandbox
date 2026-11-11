"""PG-10_C3: non-authoritative, typed decision routing over C1/C2 candidates.

A declaration of a prior decision is NOT proof it exists or is current.
No question is sent; no Phase 1 or PG-03 dispatcher is invoked.
"""
import hashlib
import json
from copy import deepcopy

SCHEMA = "PG10_C2_PRECEDENCE_LEGACY_GUARD_CANDIDATE_V1"
ROUTES = {
    "HUMAN_DECISION": "HUMAN_DECISION_PACKET_CANDIDATE",
    "TECHNICAL_DECISION": "RETURN_PG03_TECHNICAL_REVIEW",
    "IMPLEMENTATION_MISSING": "CONTINUE_IMPLEMENTATION_NOT_QUESTION",
}
class PG10C3Blocked(ValueError):
    pass

def _fail(reason):
    raise PG10C3Blocked(reason)

def _digest(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()).hexdigest()

def _ref(value):
    return isinstance(value, str) and bool(value.strip())

def prepare_pg10_c3(*, pg10_c2, routing_observations):
    """Prepare routes; do not classify or authenticate the underlying reality.

    Each observation: solution_id, issues.
    Each issue: conflict_id, issue_class, exact_query_ref, resolver_ref,
      prior_decision_ref, prior_decision_current_verified.
    issue_class: HUMAN_DECISION, TECHNICAL_DECISION, IMPLEMENTATION_MISSING,
      EVIDENCE_GAP, REQUIREMENT_GAP.
    """
    if not isinstance(pg10_c2, dict) or pg10_c2.get("schema_version") != SCHEMA:
        _fail("PG10_C3_UPSTREAM_SCHEMA_INVALID")
    sha = _digest({k: v for k, v in pg10_c2.items() if k != "candidate_sha256"})
    if pg10_c2.get("candidate_sha256") != sha:
        _fail("PG10_C3_UPSTREAM_DIGEST_INVALID")
    if (pg10_c2.get("status") != "CANDIDATE_NOT_ADMITTED"
        or pg10_c2.get("pg10_c2_pass") is not False
        or pg10_c2.get("pg10_c2_admitted") is not False
        or pg10_c2.get("production_authority") is not False
        or pg10_c2.get("handoff_allowed") is not False
        or pg10_c2.get("precedence_decided") is not False):
        _fail("PG10_C3_UPSTREAM_AUTHORITY_INVALID")
    solutions = pg10_c2.get("solutions")
    if not isinstance(solutions, list) or not solutions:
        _fail("PG10_C3_SOLUTIONS_INVALID")
    canonical = {}
    for sol in solutions:
        if not isinstance(sol, dict) or not _ref(sol.get("solution_id")):
            _fail("PG10_C3_SOLUTION_ID_INVALID")
        sid = sol["solution_id"]
        if sid in canonical or sol.get("decision_authorized") is not False:
            _fail("PG10_C3_SOLUTION_AUTHORITY_INVALID")
        actions = sol.get("conflict_actions")
        if not isinstance(actions, list):
            _fail("PG10_C3_CONFLICT_ACTIONS_INVALID")
        seen = set()
        for item in actions:
            if not isinstance(item, dict) or not _ref(item.get("conflict_id")) or item["conflict_id"] in seen:
                _fail("PG10_C3_CONFLICT_ID_INVALID")
            seen.add(item["conflict_id"])
        canonical[sid] = (sol, {x["conflict_id"]: x for x in actions})
    if not isinstance(routing_observations, list) or len(routing_observations) != len(canonical):
        _fail("PG10_C3_ROUTING_COVERAGE_INVALID")
    observed = {}
    for row in routing_observations:
        if not isinstance(row, dict) or set(row) != {"solution_id", "issues"}:
            _fail("PG10_C3_OBSERVATION_SHAPE_INVALID")
        sid = row["solution_id"]
        if not _ref(sid) or sid in observed or not isinstance(row["issues"], list):
            _fail("PG10_C3_OBSERVATION_INVALID")
        observed[sid] = row
    if set(observed) != set(canonical):
        _fail("PG10_C3_SOLUTION_COVERAGE_DRIFT")
    output = []
    for sid in sorted(canonical):
        sol, actions = canonical[sid]
        routed = []
        used = set()
        for issue in observed[sid]["issues"]:
            fields = {"conflict_id", "issue_class", "exact_query_ref",
                      "resolver_ref", "prior_decision_ref", "prior_decision_current_verified"}
            if not isinstance(issue, dict) or set(issue) != fields:
                _fail("PG10_C3_ISSUE_SHAPE_INVALID")
            cid, cls = issue["conflict_id"], issue["issue_class"]
            if cid not in actions or cid in used:
                _fail("PG10_C3_CONFLICT_COVERAGE_INVALID")
            used.add(cid)
            if cls not in set(ROUTES) | {"EVIDENCE_GAP", "REQUIREMENT_GAP"}:
                _fail("PG10_C3_ISSUE_CLASS_INVALID")
            if issue["prior_decision_current_verified"] is not False:
                _fail("PG10_C3_FORGED_DECISION_AUTHORITY")
            prior = issue["prior_decision_ref"]
            if prior is not None and not _ref(prior):
                _fail("PG10_C3_PRIOR_DECISION_REF_INVALID")
            if not _ref(issue["resolver_ref"]):
                _fail("PG10_C3_RESOLVER_REF_REQUIRED")
            exact = issue["exact_query_ref"]
            if exact is not None and not _ref(exact):
                _fail("PG10_C3_EXACT_QUERY_REF_INVALID")
            if cls in {"EVIDENCE_GAP", "REQUIREMENT_GAP"} and not _ref(exact):
                _fail("PG10_C3_EXACT_GAP_QUERY_REQUIRED")
            action = actions[cid].get("action_candidate")
            if action == "RETURN_PHASE1_A3" and cls != "REQUIREMENT_GAP":
                _fail("PG10_C3_REQUIREMENT_GAP_MISMATCH")
            if action == "QUERY_EXACT_MISSING_EVIDENCE" and cls != "EVIDENCE_GAP":
                _fail("PG10_C3_EVIDENCE_GAP_MISMATCH")
            if cls in {"REQUIREMENT_GAP", "EVIDENCE_GAP"} and action not in {
                "RETURN_PHASE1_A3", "QUERY_EXACT_MISSING_EVIDENCE"
            }:
                _fail("PG10_C3_GAP_ACTION_MISMATCH")
            if cls == "REQUIREMENT_GAP":
                route = "RETURN_PHASE1_A3"
            elif cls == "EVIDENCE_GAP":
                route = "QUERY_EXACT_MISSING_EVIDENCE"
            elif prior is not None:
                route = "CHECK_PRIOR_DECISION_CURRENTNESS_BEFORE_QUESTION"
            else:
                route = ROUTES[cls]
            routed.append({
                "conflict_id": cid, "issue_class_reported": cls,
                "route_candidate": route, "resolver_ref_reported": issue["resolver_ref"],
                "exact_query_ref_reported": exact,
                "prior_decision_ref_reported": prior,
                "prior_decision_reused": False,
                "human_question_sent": False,
                "technical_dispatch_executed": False,
                "phase1_return_executed": False,
                "route_authenticated": False,
                "duplicate_question_prevented_by_execution": False,
            })
        if used != set(actions):
            _fail("PG10_C3_CONFLICT_COVERAGE_DRIFT")
        output.append({
            "solution_id": sid,
            "routes": sorted(routed, key=lambda r: r["conflict_id"]),
            "human_decision_packet_issued": False,
            "unaffected_scope_continued": False,
            "decision_resolved": False,
        })
    result = {
        "schema_version": "PG10_C3_TYPED_ROUTING_CANDIDATE_V1",
        "status": "CANDIDATE_NOT_ADMITTED",
        "source_pg10_c2_sha256": sha,
        "routing_observations_sha256": _digest(routing_observations),
        "run_ref": pg10_c2.get("run_ref"),
        "solutions": output,
        "existing_decisions_looked_up": False,
        "duplicate_questions_checked_against_ledger": False,
        "human_only_classification_authenticated": False,
        "analysis_modified": False, "pg03_dispatched": False,
        "human_questions_sent": False, "phase1_return_executed": False,
        "pg10_c3_pass": False, "pg10_c3_admitted": False,
        "handoff_allowed": False, "production_authority": False,
        "next_gate": "VERIFY_DECISION_LEDGER_AND_ROUTE_AGAINST_AUTHENTIC_SOURCES"
    }
    result["candidate_sha256"] = _digest(result)
    return deepcopy(result)
