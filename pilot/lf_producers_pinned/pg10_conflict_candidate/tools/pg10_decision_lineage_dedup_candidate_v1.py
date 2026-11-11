"""PG-10 deterministic *candidate* guard for duplicate human questions and lineage.

The caller supplies ledger observations; these are NEVER authenticated here.
A prior decision, whether resolved or stale, must be checked before resending
a question. A resolved prior with matching key MUST NOT cause a new question.
No ledger writes, no dispatch, no authority.
"""
import hashlib
import json
from copy import deepcopy

class PG10LineageBlocked(ValueError):
    pass

def block(code):raise PG10LineageBlocked(code)
def digest(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()
def ref(x):return isinstance(x,str) and bool(x.strip())
def source(x,schema):
    if not isinstance(x,dict) or x.get("schema_version")!=schema: block("PG10_LINEAGE_SOURCE_SCHEMA")
    if x.get("candidate_sha256")!=digest({k:v for k,v in x.items() if k!="candidate_sha256"}):
        block("PG10_LINEAGE_SOURCE_HASH")
    if x.get("production_authority") is not False or x.get("handoff_allowed") is not False:
        block("PG10_LINEAGE_SOURCE_AUTHORITY")
    return x["candidate_sha256"]

def prepare_pg10_decision_lineage(*,pg08_final,pg09_c4,pg10_c3,
                                  ledger_observations,proposed_human_questions):
    h8=source(pg08_final,"PG08_C6_C7_C8_FINAL_FEEDBACK_CANDIDATE_V1")
    h9=source(pg09_c4,"PG09_C4_TYPED_ESCALATION_CANDIDATE_V1")
    h3=source(pg10_c3,"PG10_C3_TYPED_ROUTING_CANDIDATE_V1")
    if (pg08_final.get("feedback_only") is not True or pg08_final.get("final_verdict_issued") is not False
        or pg09_c4.get("status")!="CANDIDATE_NOT_ADMITTED"
        or pg10_c3.get("status")!="CANDIDATE_NOT_ADMITTED"
        or pg09_c4.get("run_ref")!=pg10_c3.get("run_ref")):
        block("PG10_LINEAGE_PREMATURE_AUTHORITY_OR_RUN_DRIFT")
    route_by_key={}
    for sol in pg10_c3.get("solutions",[]):
        for r in sol.get("routes",[]):
            key=(sol["solution_id"],r["conflict_id"])
            if key in route_by_key:block("PG10_LINEAGE_DUPLICATE_ROUTE")
            route_by_key[key]=r
    if not route_by_key:block("PG10_LINEAGE_NO_ROUTES")
    if not isinstance(ledger_observations,list) or not isinstance(proposed_human_questions,list):
        block("PG10_LINEAGE_INPUT_INVALID")
    ledger={}
    for rec in ledger_observations:
        if not isinstance(rec,dict) or set(rec)!={"solution_id","conflict_id","decision_ref",
            "decision_state","decision_question_key","currentness_ref"}:
            block("PG10_LINEAGE_LEDGER_SHAPE")
        key=(rec["solution_id"],rec["conflict_id"])
        if key not in route_by_key or key in ledger or not all(ref(rec[k]) for k in (
            "decision_ref","decision_question_key","currentness_ref")) or rec["decision_state"] not in {
            "RESOLVED","STALE","PENDING"}:
            block("PG10_LINEAGE_LEDGER_IDENTITY")
        ledger[key]=rec
    proposed=set()
    for row in proposed_human_questions:
        if not isinstance(row,dict) or set(row)!={"solution_id","conflict_id","decision_question_key"}:
            block("PG10_LINEAGE_QUESTION_SHAPE")
        key=(row["solution_id"],row["conflict_id"])
        if key not in route_by_key or key in proposed or not ref(row["decision_question_key"]):
            block("PG10_LINEAGE_QUESTION_IDENTITY")
        proposed.add(key)
        route=route_by_key[key]
        old=ledger.get(key)
        if old is not None:
            if old["decision_question_key"]!=row["decision_question_key"]:
                block("PG10_LINEAGE_PRIOR_DECISION_QUESTION_KEY_DRIFT")
            if old["decision_state"]=="RESOLVED":
                block("PG10_DUPLICATE_ANSWERED_QUESTION")
            block("PG10_PRIOR_DECISION_REQUIRES_CURRENTNESS_CHECK")
        if route["route_candidate"]!="HUMAN_DECISION_PACKET_CANDIDATE":
            block("PG10_NOT_A_NEW_HUMAN_QUESTION")
    rows=[]
    for key,route in sorted(route_by_key.items()):
        old=ledger.get(key)
        rows.append({"solution_id":key[0],"conflict_id":key[1],
            "prior_decision_ref_reported":old["decision_ref"] if old else None,
            "prior_state_reported":old["decision_state"] if old else None,
            "proposed_question_present":key in proposed,
            "reuse_decision_candidate":old is not None and old["decision_state"]=="RESOLVED",
            "ledger_authenticated":False,"human_question_sent":False,
            "duplicate_prevented_by_runtime":False})
    result={"schema_version":"PG10_DECISION_LINEAGE_DEDUP_CANDIDATE_V1",
        "status":"CANDIDATE_NOT_ADMITTED",
        "source_pg08_final_sha256":h8,"source_pg09_c4_sha256":h9,
        "source_pg10_c3_sha256":h3,
        "ledger_observations_sha256":digest(ledger_observations),
        "proposed_questions_sha256":digest(proposed_human_questions),
        "rows":rows,"decision_ledger_authenticated":False,
        "pg08_final_receipts_authenticated":False,
        "pg09_escalation_delivered":False,
        "question_sent":False,"production_authority":False,"handoff_allowed":False,
        "next_gate":"AUTHENTIC_LEDGER_READBACK_CURRENTNESS_AND_QUESTION_DEDUP"}
    result["candidate_sha256"]=digest(result)
    return deepcopy(result)
