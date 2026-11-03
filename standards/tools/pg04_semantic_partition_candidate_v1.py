"""PG-04 semantic partition candidate. Typed outcomes, not a model/judge/dispatcher."""
import hashlib
import json
from collections import defaultdict

class PartitionBlocked(ValueError):
    pass

def _block(code):
    raise PartitionBlocked(code)

def _text(v):
    return isinstance(v,str) and bool(v.strip())

def _ids(v,code,empty=False):
    if not isinstance(v,list) or (not v and not empty) or any(not _text(x) for x in v) or len(v)!=len(set(v)):
        _block(code)
    return v

def _sha(v):
    return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()

def partition_by_semantic_outcome(*,strategy,partition_contract,obligations,outcome_registry):
    """Group obligations with same evidenced outcome/binding. Dependencies only order."""
    if not isinstance(strategy,dict) or strategy.get("status")!="CANDIDATE_NOT_ADMITTED" or strategy.get("production_authority") is not False or strategy.get("handoff_allowed") is not False:
        _block("STRATEGY_NOT_CANDIDATE")
    digest=strategy.get("candidate_sha256")
    if not _text(digest) or len(digest)!=64 or _sha({k:v for k,v in strategy.items() if k!="candidate_sha256"})!=digest:
        _block("STRATEGY_DIGEST_DRIFT")
    reqs=set(_ids(strategy.get("requirement_ids"),"REQUIREMENTS_INVALID"))
    accs=set(_ids(strategy.get("acceptance_ids"),"ACCEPTANCE_INVALID"))
    scopes=set(_ids(strategy.get("scope_ids"),"SCOPES_INVALID"))
    c=partition_contract
    if not isinstance(c,dict) or c.get("schema_version")!="PROGRAMMING_SOLUTION_PARTITION_CONTRACT_V1" or c.get("unit")!="PG-04" or c.get("runtime_activation") is not False or c.get("production_activation") is not False:
        _block("CONTRACT_NOT_CANDIDATE")
    p,coverage=c.get("partition_policy"),c.get("coverage")
    if not isinstance(p,dict) or not isinstance(coverage,dict) or p.get("partition_unit")!="SOLUTION" or p.get("canonical_spec_count")!=1 or p.get("minimum_rule")!="SMALLEST_COHERENT_VALID_CHANGE" or coverage.get("material_requirement_coverage_required_percent")!=100 or coverage.get("acceptance_obligation_coverage_required_percent")!=100:
        _block("PARTITION_POLICY_DRIFT")
    for k in ("semantic_boundary_first","dependency_closure_required","risk_boundary_considered","write_scope_boundary_considered","token_count_alone_must_not_define_partition","file_count_alone_must_not_define_partition","shared_contracts_referenced_not_copied"):
        if p.get(k) is not True:
            _block("PARTITION_POLICY_DRIFT")
    if not isinstance(outcome_registry,list) or not outcome_registry:
        _block("OUTCOME_REGISTRY_MISSING")
    outcomes={}
    for o in outcome_registry:
        if not isinstance(o,dict) or any(not _text(o.get(k)) for k in ("outcome_id","business_outcome","evidence_ref")):
            _block("OUTCOME_EVIDENCE_INVALID")
        if o["outcome_id"] in outcomes:
            _block("OUTCOME_DUPLICATE")
        outcomes[o["outcome_id"]]=o
    if not isinstance(obligations,list) or not obligations:
        _block("OBLIGATIONS_MISSING")
    atoms={};req_owners={};acc_owners={}
    for a in obligations:
        if not isinstance(a,dict) or any(not _text(a.get(k)) for k in ("atom_id","outcome_id","source_ref","scope_id","risk_level","write_scope_reason","semantic_rationale")):
            _block("OBLIGATION_EVIDENCE_INVALID")
        oid=a["atom_id"]
        if oid in atoms:
            _block("ATOM_DUPLICATE")
        if a["outcome_id"] not in outcomes or a["scope_id"] not in scopes:
            _block("SOURCE_SCOPE_OR_OUTCOME_UNKNOWN")
        if a["risk_level"] not in ("LOW","MEDIUM","HIGH"):
            _block("RISK_LEVEL_INVALID")
        _ids(a.get("write_scope"),"WRITE_SCOPE_INVALID")
        _ids(a.get("shared_contract_refs"),"SHARED_CONTRACT_REFS_INVALID",True)
        if "shared_contracts" in a or "shared_contract_definition" in a:
            _block("INLINE_SHARED_CONTRACT_FORBIDDEN")
        state=a.get("implementation_state")
        if state=="EXISTING":
            if not _text(a.get("as_is_ref")) or not _text(a.get("delta_ref")):
                _block("EXISTING_DELTA_MISSING")
            binding=("EXISTING",a["as_is_ref"],a["delta_ref"])
        elif state=="NEW":
            if not _text(a.get("bounded_reuse_assessment_ref")):
                _block("NEW_REUSE_EVIDENCE_MISSING")
            binding=("NEW",a["bounded_reuse_assessment_ref"])
        else:
            _block("IMPLEMENTATION_STATE_UNKNOWN")
        r=_ids(a.get("requirement_ids"),"ATOM_REQUIREMENTS_INVALID",True)
        t=_ids(a.get("acceptance_ids"),"ATOM_ACCEPTANCE_INVALID",True)
        if not r and not t:
            _block("ATOM_HAS_NO_OBLIGATION")
        for values,owners in ((r,req_owners),(t,acc_owners)):
            for item in values:
                if item in owners:
                    _block("DUPLICATE_OBLIGATION_OWNERSHIP")
                owners[item]=oid
        _ids(a.get("depends_on",[]),"DEPENDENCIES_INVALID",True)
        _ids(a.get("coimplement_with",[]),"COIMPLEMENT_INVALID",True)
        if a.get("coimplement_with") and not _text(a.get("coimplement_evidence_ref")):
            _block("COIMPLEMENT_EVIDENCE_MISSING")
        atoms[oid]=dict(a,_binding=binding)
    if set(req_owners)!=reqs or set(acc_owners)!=accs:
        _block("COVERAGE_INCOMPLETE_OR_FOREIGN")
    for oid,a in atoms.items():
        if oid in a["depends_on"] or oid in a["coimplement_with"]:
            _block("SELF_DEPENDENCY_OR_COIMPLEMENT")
        if any(x not in atoms for x in a["depends_on"]+a["coimplement_with"]):
            _block("UNKNOWN_ATOM_DEPENDENCY")
    # No file/token heuristic: group only evidence-labeled outcomes and
    # compatible implementation bindings. Explicit coimplementation is reciprocal.
    groups=defaultdict(set)
    for oid,a in atoms.items():
        groups[(a["outcome_id"],a["_binding"],"HIGH" if a["risk_level"]=="HIGH" else "NON_HIGH")].add(oid)
    parent={oid:oid for oid in atoms}
    def root(x):
        while parent[x]!=x:
            parent[x]=parent[parent[x]]
            x=parent[x]
        return x
    def merge(a,b):
        a,b=root(a),root(b)
        if a!=b:parent[max(a,b)]=min(a,b)
    for members in groups.values():
        for x in members:merge(min(members),x)
    for oid,a in atoms.items():
        for other in a["coimplement_with"]:
            b=atoms[other]
            if oid not in b["coimplement_with"] or not _text(b.get("coimplement_evidence_ref")):
                _block("COIMPLEMENT_NOT_RECIPROCAL")
            if a["_binding"]!=b["_binding"]:
                _block("COIMPLEMENT_STATE_CONFLICT")
            if a["risk_level"]!=b["risk_level"] and "HIGH" in (a["risk_level"],b["risk_level"]):
                _block("COIMPLEMENT_RISK_CONFLICT")
            merge(oid,other)
    merged=defaultdict(list)
    for oid in sorted(atoms):merged[root(oid)].append(oid)
    clusters=sorted(merged.values(),key=lambda x:x[0])
    atom_solution={oid:f"SOL-{i:03d}" for i,members in enumerate(clusters,1) for oid in members}
    solutions=[]
    for i,members in enumerate(clusters,1):
        sid=f"SOL-{i:03d}"
        rows=[atoms[x] for x in members]
        outcome_ids=sorted({x["outcome_id"] for x in rows})
        binding=rows[0]["_binding"]
        solution={
            "id":sid,"strategy_ref":digest,"partition_basis":"SEMANTIC_SOLUTION",
            "business_outcome":" | ".join(outcomes[x]["business_outcome"] for x in outcome_ids),
            "outcome_ids":outcome_ids,
            "semantic_boundary_reason":"Source-linked outcomes and reciprocal atomicity only",
            "risk_boundary_reason":"Original risks preserved: "+",".join(sorted({x["risk_level"] for x in rows})),
            "write_scope_reason":"Original write-scope reasons preserved per atom",
            "write_scope":sorted({v for x in rows for v in x["write_scope"]}),
            "shared_contract_refs":sorted({v for x in rows for v in x["shared_contract_refs"]}),
            "implementation_state":binding[0],
            "requirement_ids":sorted({v for x in rows for v in x["requirement_ids"]}),
            "acceptance_ids":sorted({v for x in rows for v in x["acceptance_ids"]}),
            "depends_on":sorted({atom_solution[d] for x in rows for d in x["depends_on"] if atom_solution[d]!=sid}),
            "atom_ids":members,
            "source_bindings":[
                {"atom_id":x["atom_id"],"source_ref":x["source_ref"],"scope_id":x["scope_id"],
                 "outcome_evidence_ref":outcomes[x["outcome_id"]]["evidence_ref"],
                 "semantic_rationale":x["semantic_rationale"],
                 "write_scope_reason":x["write_scope_reason"],"risk_level":x["risk_level"]}
                for x in rows],
        }
        if binding[0]=="EXISTING":solution["as_is_ref"],solution["delta_ref"]=binding[1:]
        else:solution["bounded_reuse_assessment_ref"]=binding[1]
        solutions.append(solution)
    graph={x["id"]:x["depends_on"] for x in solutions}
    visiting=set();visited=set()
    def visit(s):
        if s in visiting:_block("SOLUTION_DEPENDENCY_CYCLE")
        if s in visited:return
        visiting.add(s)
        for d in graph[s]:visit(d)
        visiting.remove(s);visited.add(s)
    for sid in sorted(graph):visit(sid)
    result={"schema_version":"PG04_SEMANTIC_PARTITION_CANDIDATE_V1",
            "status":"CANDIDATE_NOT_ADMITTED","production_authority":False,
            "dispatch_allowed":False,"handoff_allowed":False,
            "semantic_judge_executed":False,"source_authenticity":"UNVERIFIED",
            "strategy_sha256":digest,"solutions":solutions,
            "coverage":{"requirements":len(req_owners),"acceptance":len(acc_owners),"orphans":0,"duplicate_owners":0},
            "semantic_basis":"TYPED_OUTCOME_AND_EXPLICIT_COHESION_NOT_MODEL_INFERENCE"}
    result["candidate_sha256"]=_sha(result)
    return result
