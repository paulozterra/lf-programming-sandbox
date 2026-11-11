"""PG-10_C4 candidate human-decision packets; no question delivery or resume authority."""
import hashlib
import json
from copy import deepcopy

SCHEMA = "PG10_C3_TYPED_ROUTING_CANDIDATE_V1"
HUMAN_ROUTE = "HUMAN_DECISION_PACKET_CANDIDATE"

class PG10C4Blocked(ValueError):
    pass

def fail(code):
    raise PG10C4Blocked(code)

def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()

def ref(value):
    return isinstance(value, str) and bool(value.strip())

def refs(value):
    return isinstance(value, list) and bool(value) and all(map(ref, value)) and len(value) == len(set(value))

def prepare_pg10_c4(*, pg10_c3, decision_observations):
    """Prepare packets only for declared HUMAN_ROUTE issues.

    decision_observations: [{solution_id, packets: [{conflict_id, question,
    options:[{option_id, description, consequence}], recommended_option_id,
    recommendation_reason, risk_if_undecided, source_refs,
    affected_scope_refs, resume_condition, ready_unaffected_scope_refs}]}]
    """
    if not isinstance(pg10_c3, dict) or pg10_c3.get("schema_version") != SCHEMA:
        fail("PG10_C4_SOURCE_SCHEMA_INVALID")
    sha = digest({k: v for k, v in pg10_c3.items() if k != "candidate_sha256"})
    if pg10_c3.get("candidate_sha256") != sha:
        fail("PG10_C4_SOURCE_DIGEST_INVALID")
    flags = ["pg10_c3_pass", "pg10_c3_admitted", "handoff_allowed",
             "production_authority", "human_questions_sent",
             "existing_decisions_looked_up", "duplicate_questions_checked_against_ledger"]
    if pg10_c3.get("status") != "CANDIDATE_NOT_ADMITTED" or any(pg10_c3.get(f) is not False for f in flags):
        fail("PG10_C4_PREMATURE_AUTHORITY")
    solutions = pg10_c3.get("solutions")
    if not isinstance(solutions, list) or not solutions:
        fail("PG10_C4_SOLUTIONS_INVALID")
    lookup = {}
    for s in solutions:
        if not isinstance(s, dict) or not ref(s.get("solution_id")) or s["solution_id"] in lookup:
            fail("PG10_C4_SOLUTION_ID_INVALID")
        if s.get("human_decision_packet_issued") is not False or s.get("decision_resolved") is not False:
            fail("PG10_C4_SOURCE_STATE_INVALID")
        routes = s.get("routes")
        if not isinstance(routes, list):
            fail("PG10_C4_ROUTES_INVALID")
        route_ids = set()
        humans = set()
        for route in routes:
            cid = route.get("conflict_id") if isinstance(route, dict) else None
            if not ref(cid) or cid in route_ids:
                fail("PG10_C4_ROUTE_ID_INVALID")
            route_ids.add(cid)
            if route.get("route_candidate") == HUMAN_ROUTE:
                if route.get("issue_class_reported") != "HUMAN_DECISION" or route.get("prior_decision_ref_reported") is not None:
                    fail("PG10_C4_HUMAN_ROUTE_INVALID")
                humans.add(cid)
        lookup[s["solution_id"]] = humans
    if not isinstance(decision_observations, list) or len(decision_observations) != len(lookup):
        fail("PG10_C4_OBSERVATION_COVERAGE_INVALID")
    observations = {}
    for row in decision_observations:
        if not isinstance(row, dict) or set(row) != {"solution_id", "packets"}:
            fail("PG10_C4_OBSERVATION_SHAPE_INVALID")
        sid = row["solution_id"]
        if not ref(sid) or sid in observations or not isinstance(row["packets"], list):
            fail("PG10_C4_OBSERVATION_INVALID")
        observations[sid] = row["packets"]
    if set(observations) != set(lookup):
        fail("PG10_C4_SOLUTION_COVERAGE_DRIFT")
    output = []
    for sid in sorted(lookup):
        prepared = []
        ids = set()
        for packet in observations[sid]:
            fields = {"conflict_id", "question", "options", "recommended_option_id",
                      "recommendation_reason", "risk_if_undecided", "source_refs",
                      "affected_scope_refs", "resume_condition", "ready_unaffected_scope_refs"}
            if not isinstance(packet, dict) or set(packet) != fields:
                fail("PG10_C4_PACKET_SHAPE_INVALID")
            cid = packet["conflict_id"]
            if cid not in lookup[sid] or cid in ids:
                fail("PG10_C4_NON_HUMAN_OR_DUPLICATE_PACKET")
            ids.add(cid)
            for key in ("question", "recommended_option_id", "recommendation_reason",
                        "risk_if_undecided", "resume_condition"):
                if not ref(packet[key]):
                    fail("PG10_C4_MISSING_DECISION_CONTENT")
            if not refs(packet["source_refs"]) or not refs(packet["affected_scope_refs"]):
                fail("PG10_C4_REFERENCES_INVALID")
            ready = packet["ready_unaffected_scope_refs"]
            if not isinstance(ready, list) or not all(map(ref, ready)) or len(set(ready)) != len(ready):
                fail("PG10_C4_READY_SCOPE_INVALID")
            if set(ready) & set(packet["affected_scope_refs"]):
                fail("PG10_C4_SCOPE_OVERLAP")
            options = packet["options"]
            if not isinstance(options, list) or len(options) < 2:
                fail("PG10_C4_OPTIONS_INSUFFICIENT")
            option_ids = set()
            for option in options:
                if not isinstance(option, dict) or set(option) != {"option_id", "description", "consequence"}:
                    fail("PG10_C4_OPTION_SHAPE_INVALID")
                if not all(ref(option[k]) for k in ("option_id", "description", "consequence")) or option["option_id"] in option_ids:
                    fail("PG10_C4_OPTION_INVALID")
                option_ids.add(option["option_id"])
            if packet["recommended_option_id"] not in option_ids:
                fail("PG10_C4_RECOMMENDATION_NOT_IN_OPTIONS")
            prepared.append({
                "schema_version": "PROGRAMMING_HUMAN_DECISION_PACKET_V1",
                "solution_id": sid, "conflict_id": cid,
                "question_candidate": packet["question"],
                "options_candidate": deepcopy(options),
                "recommendation_candidate": packet["recommended_option_id"],
                "recommendation_reason_reported": packet["recommendation_reason"],
                "risk_if_undecided_reported": packet["risk_if_undecided"],
                "source_refs_reported": sorted(packet["source_refs"]),
                "affected_scope_refs_reported": sorted(packet["affected_scope_refs"]),
                "ready_unaffected_scope_refs_reported": sorted(ready),
                "resume_condition_candidate": packet["resume_condition"],
                "prior_decision_lookup_verified": False,
                "scope_currentness_verified": False,
                "question_sent": False,
                "decision_recorded": False, "affected_scope_resumed": False,
                "unaffected_ready_scope_executed": False,
                "status": "CANDIDATE_NOT_ADMITTED"
            })
        if ids != lookup[sid]:
            fail("PG10_C4_MISSING_HUMAN_PACKET")
        output.append({"solution_id": sid, "packets": sorted(prepared, key=lambda p: p["conflict_id"])})
    result = {
        "schema_version": "PG10_C4_HUMAN_DECISION_PACKETS_CANDIDATE_V1",
        "status": "CANDIDATE_NOT_ADMITTED",
        "source_pg10_c3_sha256": sha,
        "decision_observations_sha256": digest(decision_observations),
        "run_ref": pg10_c3.get("run_ref"),
        "solutions": output,
        "decision_ledger_readback_verified": False,
        "ready_scope_eligibility_verified": False,
        "human_questions_sent": False,
        "scope_restarted": False,
        "analysis_modified": False, "pg10_c4_pass": False, "pg10_c4_admitted": False,
        "handoff_allowed": False, "production_authority": False,
        "next_gate": "AUTHENTIC_DECISION_DEDUP_AND_SCOPE_RESUME_QUALIFICATION"
    }
    result["candidate_sha256"] = digest(result)
    return deepcopy(result)
