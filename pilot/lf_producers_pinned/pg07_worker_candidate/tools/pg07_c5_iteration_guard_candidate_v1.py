"""PG-07_C5: fail-closed candidate iteration drift classifier.

Detects declared objective/acceptance/scope drift and creates PG-10 referral
requests. Not a runtime monitor: caller-supplied evidence is not authenticated.
Never silently rewrites a task, invokes a worker or closes a checkpoint.
"""
import hashlib
import json
import re
from copy import deepcopy

class IterationGuardBlocked(ValueError):pass
_SHA=re.compile(r"^[0-9a-f]{64}$")
_MUTABLE={"objective","acceptance","write_scope"}
def _fail(s):raise IterationGuardBlocked(s)
def _hash(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()
def _ref(s):return isinstance(s,str) and bool(s.strip())
def _frozen(v,schema):
    if not isinstance(v,dict) or v.get("schema_version")!=schema:_fail("PG07_C5_SOURCE_SCHEMA_INVALID")
    sha=v.get("candidate_sha256")
    if not isinstance(sha,str) or not _SHA.fullmatch(sha) or sha!=_hash({k:x for k,x in v.items() if k!="candidate_sha256"}):
        _fail("PG07_C5_SOURCE_HASH_DRIFT")
    return sha

def prepare_pg07_c5(*,pg07_c2,pg07_c3,pg07_c4,iteration_proposals):
    c2sha=_frozen(pg07_c2,"PG07_C2_WORKER_TASK_BATCH_CANDIDATE_V1")
    c3sha=_frozen(pg07_c3,"PG07_C3_CONTEXT_PROJECTION_CANDIDATE_V1")
    c4sha=_frozen(pg07_c4,"PG07_C4_CONTRACT_FIRST_STANDARDS_CANDIDATE_V1")
    if (pg07_c3.get("source_pg07_c2_sha256")!=c2sha
        or pg07_c4.get("source_pg07_c2_sha256")!=c2sha
        or pg07_c4.get("source_pg07_c3_sha256")!=c3sha
        or any(x.get("production_authority") is not False or x.get("handoff_allowed") is not False
               or x.get("dispatch_allowed") is not False or x.get("worker_invoked") is not False
               for x in (pg07_c2,pg07_c3,pg07_c4))):
        _fail("PG07_C5_SOURCE_CHAIN_INVALID")
    payloads=pg07_c2.get("worker_payloads")
    if not isinstance(payloads,list) or not payloads:_fail("PG07_C5_TASK_SET_MISSING")
    specs={}
    for item in payloads:
        if not isinstance(item,dict) or not _ref(item.get("solution_id")) or item["solution_id"] in specs:
            _fail("PG07_C5_TASK_ID_INVALID")
        spec=item.get("worker_visible_task_spec")
        if not isinstance(spec,dict) or not isinstance(spec.get("functional_contract"),dict) or not isinstance(spec.get("scope"),dict):
            _fail("PG07_C5_SPEC_INCOMPLETE")
        if item.get("worker_task_spec_sha256")!=_hash(spec):
            _fail("PG07_C5_TASK_SPEC_DIGEST_DRIFT")
        specs[item["solution_id"]]=item
    if not isinstance(iteration_proposals,list):_fail("PG07_C5_ITERATION_LIST_INVALID")
    by_solution={sid:[] for sid in specs}
    ids=set()
    for proposal in iteration_proposals:
        if not isinstance(proposal,dict) or set(proposal)!={
            "iteration_id","solution_id","previous_iteration_ref","objective_ref",
            "change_reason","proposed_diff_ref","proposed_diff_sha256",
            "baseline_bindings","proposed_bindings","declared_changed_fields",
            "evidence_refs"}:
            _fail("PG07_C5_PROPOSAL_SCHEMA_INVALID")
        iid,sid=proposal["iteration_id"],proposal["solution_id"]
        if sid not in specs or not _ref(iid) or iid in ids:
            _fail("PG07_C5_ITERATION_ID_INVALID")
        ids.add(iid)
        if (not _ref(proposal["objective_ref"]) or not _ref(proposal["change_reason"])
            or not _ref(proposal["proposed_diff_ref"])
            or not isinstance(proposal["proposed_diff_sha256"],str)
            or not _SHA.fullmatch(proposal["proposed_diff_sha256"])
            or not isinstance(proposal["evidence_refs"],list)
            or not proposal["evidence_refs"]
            or any(not _ref(r) for r in proposal["evidence_refs"])
            or len(set(proposal["evidence_refs"]))!=len(proposal["evidence_refs"])):
            _fail("PG07_C5_ITERATION_EVIDENCE_INVALID")
        prev=proposal["previous_iteration_ref"]
        if prev is not None and not _ref(prev):_fail("PG07_C5_PREVIOUS_ITERATION_REF_INVALID")
        if (not isinstance(proposal["declared_changed_fields"],list)
            or len(set(proposal["declared_changed_fields"]))!=len(proposal["declared_changed_fields"])
            or not set(proposal["declared_changed_fields"]).issubset(_MUTABLE)):
            _fail("PG07_C5_CHANGE_FIELDS_INVALID")
        baseline=proposal["baseline_bindings"]
        candidate=proposal["proposed_bindings"]
        if (not isinstance(baseline,dict) or set(baseline)!=_MUTABLE
            or not isinstance(candidate,dict) or set(candidate)!=_MUTABLE
            or any(not isinstance(baseline[k],str) or not _SHA.fullmatch(baseline[k])
                   or not isinstance(candidate[k],str) or not _SHA.fullmatch(candidate[k]) for k in _MUTABLE)):
            _fail("PG07_C5_MATERIAL_BINDING_INVALID")
        spec=specs[sid]["worker_visible_task_spec"]
        canonical={
            "objective":_hash(spec["objective"]),
            "acceptance":_hash(spec["functional_contract"].get("acceptance_criteria")),
            "write_scope":_hash({
                "scope":spec["scope"],
                "write_path_patterns":spec.get("write_path_patterns"),
                "protected_path_patterns":spec.get("protected_path_patterns"),
                "allow_deletions":spec.get("allow_deletions")
            }),
        }
        if baseline!=canonical:_fail("PG07_C5_BASELINE_NOT_CANONICAL_TASK")
        observed=sorted(k for k in _MUTABLE if baseline[k]!=candidate[k])
        declared=sorted(proposal["declared_changed_fields"])
        # Do not allow declarative denial of a changed objective/acceptance/scope.
        if observed!=declared:_fail("PG07_C5_UNDECLARED_MATERIAL_CHANGE")
        by_solution[sid].append(proposal)
    rows=[]
    referrals=[]
    for sid in sorted(specs):
        proposals=by_solution[sid]
        if proposals:
            # Strict sequencing is mandatory; don't infer history from ordering.
            for i,p in enumerate(proposals):
                if i==0 and p["previous_iteration_ref"] is not None:
                    _fail("PG07_C5_ITERATION_CHAIN_UNBOUND")
                if i>0 and p["previous_iteration_ref"]!=proposals[i-1]["iteration_id"]:
                    _fail("PG07_C5_ITERATION_CHAIN_DRIFT")
        reports=[]
        for i,p in enumerate(proposals):
            changed=p["declared_changed_fields"]
            requires_decision=bool(changed)
            if requires_decision:
                referrals.append({
                    "solution_id":sid,
                    "iteration_id":p["iteration_id"],
                    "routing_checkpoint":"PG-10",
                    "trigger":"MATERIAL_OBJECTIVE_ACCEPTANCE_OR_SCOPE_CHANGE",
                    "changed_fields":sorted(changed),
                    "evidence_refs":deepcopy(p["evidence_refs"]),
                    "route_action":"REQUEST_GOVERNED_DECISION_NOT_SILENT_REWRITE",
                    "pg10_decision_executed":False,
                })
            reports.append({
                "iteration_id":p["iteration_id"],
                "previous_iteration_ref":p["previous_iteration_ref"],
                "objective_ref":p["objective_ref"],
                "change_reason":p["change_reason"],
                "proposed_diff_ref":p["proposed_diff_ref"],
                "proposed_diff_sha256":p["proposed_diff_sha256"],
                "evidence_refs":deepcopy(p["evidence_refs"]),
                "changed_fields":sorted(changed),
                "diagnostic_status":("BLOCK_ROUTE_PG10" if requires_decision
                                     else "NO_DECLARED_MATERIAL_DRIFT_UNVERIFIED"),
                "worker_execution_receipt_verified":False,
                "real_diff_verified":False,
                "iteration_applied":False,
            })
        rows.append({"solution_id":sid,"iterations":reports,
                     "diagnostic_status":"BLOCK_ROUTE_PG10" if any(r["changed_fields"] for r in reports)
                                          else "NO_DECLARED_MATERIAL_DRIFT_UNVERIFIED",
                     "write_allowed":False})
    result={
        "schema_version":"PG07_C5_ITERATION_GUARD_CANDIDATE_V1",
        "status":"CANDIDATE_NOT_ADMITTED",
        "source_pg07_c2_sha256":c2sha,
        "source_pg07_c3_sha256":c3sha,
        "source_pg07_c4_sha256":c4sha,
        "solutions":rows,
        "pg10_referral_requests":referrals,
        "material_change_no_silent_rewrite":True,
        "source_evidence_authenticated":False,
        "real_diff_verified":False,
        "worker_receipts_verified":False,
        "pg10_routing_executed":False,
        "worker_invoked":False,
        "iteration_applied":False,
        "dispatch_allowed":False,
        "write_allowed":False,
        "production_authority":False,
        "handoff_allowed":False,
        "next_gate":"REAL_WORKER_ITERATION_RECEIPTS_AND_PG10_GOVERNED_ROUTING"
    }
    result["candidate_sha256"]=_hash(result)
    return result
