"""PG-04_C6 explicit repartition proposal for PG07 RED (source-only, no execution).

Requires an externally justified, atomic partition of the *original atoms*.
Never derives semantic boundaries from file counts or token totals, never invokes
CONTEXT_BUDGET_GOVERNANCE, and never grants production or review authority.
"""
import copy
import hashlib
import json

class RepartitionBlocked(ValueError):
    pass

def _deny(code):
    raise RepartitionBlocked(code)

def _hash(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()

def _text(value):
    return isinstance(value,str) and bool(value.strip())

def _ids(value):
    return isinstance(value,list) and all(_text(v) for v in value) and len(value)==len(set(value))

def _visit_dag(solutions):
    graph={row["id"]:row["depends_on"] for row in solutions}
    if len(graph)!=len(solutions):
        _deny("SOLUTION_DUPLICATE")
    active=set()
    finished=set()
    def visit(node):
        if node in active:_deny("REPARTITION_DEPENDENCY_CYCLE")
        if node in finished:return
        if node not in graph:_deny("REPARTITION_UNKNOWN_DEPENDENCY")
        active.add(node)
        for dep in graph[node]:visit(dep)
        active.remove(node)
        finished.add(node)
    for node in graph:visit(node)

def propose_repartition(*,partition,budget_edge,original_obligations,split_plan):
    if not isinstance(partition,dict) or partition.get("schema_version")!="PG04_SEMANTIC_PARTITION_CANDIDATE_V1" or partition.get("status")!="CANDIDATE_NOT_ADMITTED" or partition.get("production_authority") is not False:
        _deny("SOURCE_PARTITION_NOT_CANDIDATE")
    psha=partition.get("candidate_sha256")
    if not _text(psha) or psha!=_hash({k:v for k,v in partition.items() if k!="candidate_sha256"}):
        _deny("SOURCE_PARTITION_DIGEST_DRIFT")
    if not isinstance(budget_edge,dict) or budget_edge.get("schema_version")!="PG04_C6_BUDGET_REPAIR_EDGE_CANDIDATE_V1" or budget_edge.get("status")!="CANDIDATE_NOT_ADMITTED":
        _deny("PG07_REPAIR_EDGE_INVALID")
    edge_sha=budget_edge.get("candidate_sha256")
    if not _text(edge_sha) or edge_sha!=_hash({k:v for k,v in budget_edge.items() if k!="candidate_sha256"}):
        _deny("PG07_REPAIR_EDGE_DIGEST_DRIFT")
    if budget_edge.get("partition_sha256")!=psha or budget_edge.get("pg07_reported_context_status")!="RED" or budget_edge.get("repair_required") is not True or budget_edge.get("budget_readback_attested") is not False or budget_edge.get("production_authority") is not False:
        _deny("PG07_RED_REPAIR_NOT_ESTABLISHED")
    sols=partition.get("solutions")
    if not isinstance(sols,list) or not sols or any(not isinstance(sol,dict) or not _text(sol.get("id")) for sol in sols):
        _deny("SOURCE_SOLUTIONS_INVALID")
    sol_by_id={sol["id"]:sol for sol in sols}
    if len(sol_by_id)!=len(sols):_deny("SOURCE_SOLUTIONS_INVALID")
    target_id=budget_edge.get("solution_id")
    if target_id not in sol_by_id:_deny("REPARTITION_TARGET_UNKNOWN")
    target=sol_by_id[target_id]
    if not isinstance(split_plan,dict) or set(split_plan)!={"target_solution_id","separation_evidence_ref","groups","jit_attempt_disposition"} or split_plan["target_solution_id"]!=target_id:
        _deny("SPLIT_PLAN_INVALID")
    if not _text(split_plan["separation_evidence_ref"]):
        _deny("SPLIT_SEMANTIC_EVIDENCE_MISSING")
    if split_plan["jit_attempt_disposition"] not in ("INSUFFICIENT_WITH_EVIDENCE","NOT_APPLICABLE_WITH_EVIDENCE"):
        _deny("SPLIT_JIT_REVIEW_REQUIRED")
    groups=split_plan["groups"]
    if not isinstance(groups,list) or len(groups)<2:
        _deny("SPLIT_REQUIRES_MULTIPLE_GROUPS")
    old_ids=target.get("atom_ids")
    old_reqs=target.get("requirement_ids")
    old_accs=target.get("acceptance_ids")
    if not _ids(old_ids) or not old_ids or not _ids(old_reqs) or not _ids(old_accs):
        _deny("SOURCE_ATOM_COVERAGE_INVALID")
    if not isinstance(original_obligations,list) or len(original_obligations)!=len(old_ids):
        _deny("SOURCE_ATOM_COVERAGE_INVALID")
    atoms={}
    for atom in original_obligations:
        if not isinstance(atom,dict) or not _text(atom.get("atom_id")) or atom["atom_id"] in atoms:
            _deny("SOURCE_ATOM_COVERAGE_INVALID")
        atoms[atom["atom_id"]]=atom
    if set(atoms)!=set(old_ids):
        _deny("SOURCE_ATOM_COVERAGE_INVALID")
    seen_req=[]
    seen_acc=[]
    source_bindings=target.get("source_bindings")
    if not isinstance(source_bindings,list) or len(source_bindings)!=len(atoms):
        _deny("SOURCE_BINDINGS_INCOMPLETE")
    binds={}
    for ref in source_bindings:
        if not isinstance(ref,dict) or not _text(ref.get("atom_id")) or ref["atom_id"] in binds:
            _deny("SOURCE_BINDINGS_INCOMPLETE")
        binds[ref["atom_id"]]=ref
    if set(binds)!=set(atoms):_deny("SOURCE_BINDINGS_INCOMPLETE")
    for atom_id,atom in atoms.items():
        if any(not _ids(atom.get(k)) for k in ("requirement_ids","acceptance_ids","depends_on","coimplement_with","write_scope","shared_contract_refs")):
            _deny("SOURCE_ATOM_INVALID")
        if not atom["requirement_ids"] and not atom["acceptance_ids"]:
            _deny("SOURCE_ATOM_INVALID")
        if atom.get("source_ref")!=binds[atom_id].get("source_ref") or atom.get("scope_id")!=binds[atom_id].get("scope_id") or atom.get("implementation_state")!=binds[atom_id].get("implementation_state"):
            _deny("SOURCE_ATOM_BINDING_DRIFT")
        state=atom["implementation_state"]
        if state=="EXISTING":
            fields=("as_is_ref","delta_ref")
        elif state=="NEW":
            fields=("bounded_reuse_assessment_ref",)
        else:_deny("SOURCE_IMPLEMENTATION_STATE_INVALID")
        if any(not _text(atom.get(k)) or atom[k]!=binds[atom_id].get(k) for k in fields):
            _deny("SOURCE_ATOM_BINDING_DRIFT")
        seen_req.extend(atom["requirement_ids"])
        seen_acc.extend(atom["acceptance_ids"])
    if not _ids(seen_req) or not _ids(seen_acc) or set(seen_req)!=set(old_reqs) or set(seen_acc)!=set(old_accs):
        _deny("SOURCE_MATERIAL_COVERAGE_DRIFT")
    new_ids=[]
    owner={}
    for group in groups:
        if not isinstance(group,dict) or set(group)!={"solution_id","atom_ids","semantic_boundary_reason","evidence_ref"}:
            _deny("SPLIT_GROUP_INVALID")
        sid=group["solution_id"]
        if not _text(sid) or sid in new_ids or sid in sol_by_id:
            _deny("SPLIT_SOLUTION_ID_INVALID")
        if not _text(group["semantic_boundary_reason"]) or not _text(group["evidence_ref"]) or not _ids(group["atom_ids"]) or not group["atom_ids"]:
            _deny("SPLIT_GROUP_EVIDENCE_INVALID")
        new_ids.append(sid)
        for atom_id in group["atom_ids"]:
            if atom_id in owner:_deny("SPLIT_DUPLICATE_ATOM")
            if atom_id not in atoms:_deny("SPLIT_FOREIGN_ATOM")
            owner[atom_id]=sid
    if set(owner)!=set(atoms):
        _deny("SPLIT_ATOM_COVERAGE_INCOMPLETE")
    for atom_id,atom in atoms.items():
        for linked in atom["coimplement_with"]:
            if linked not in atoms or owner[linked]!=owner[atom_id]:
                _deny("SPLIT_ATOMICITY_VIOLATION")
    additions=[]
    for group in groups:
        sid=group["solution_id"]
        members=sorted(group["atom_ids"])
        rows=[atoms[x] for x in members]
        reqs=sorted({r for row in rows for r in row["requirement_ids"]})
        accs=sorted({a for row in rows for a in row["acceptance_ids"]})
        deps=set(target.get("depends_on",[]))
        for atom in rows:
            for dep in atom["depends_on"]:
                if dep in atoms and owner[dep]!=sid:
                    deps.add(owner[dep])
                elif dep not in atoms:
                    _deny("SPLIT_EXTERNAL_ATOM_DEPENDENCY_UNRESOLVED")
        new=copy.deepcopy(target)
        new.update({
            "id":sid,"atom_ids":members,
            "requirement_ids":reqs,"acceptance_ids":accs,
            "depends_on":sorted(deps),
            "write_scope":sorted({scope for row in rows for scope in row["write_scope"]}),
            "shared_contract_refs":sorted({ref for row in rows for ref in row["shared_contract_refs"]}),
            "source_bindings":[copy.deepcopy(binds[x]) for x in members],
            "semantic_boundary_reason":group["semantic_boundary_reason"],
            "repartition_evidence_ref":group["evidence_ref"],
            "repartition_origin":target_id,
        })
        # The original solution has one consistent implementation binding.
        if any(row["implementation_state"]!=new["implementation_state"] for row in rows):
            _deny("SPLIT_IMPLEMENTATION_STATE_CONFLICT")
        additions.append(new)
    # Preserve all downstream consumers by conservatively requiring every child;
    # any later narrowing requires separate evidence and reviewer approval.
    proposed=[]
    downstream=[]
    for sol in sols:
        if sol["id"]==target_id:continue
        row=copy.deepcopy(sol)
        if target_id in row.get("depends_on",[]):
            row["depends_on"]=sorted((set(row["depends_on"])-{target_id})|set(new_ids))
            downstream.append(row["id"])
        proposed.append(row)
    proposed.extend(additions)
    _visit_dag(proposed)
    all_old_reqs=sorted(r for sol in sols for r in sol["requirement_ids"])
    all_new_reqs=sorted(r for sol in proposed for r in sol["requirement_ids"])
    all_old_accs=sorted(a for sol in sols for a in sol["acceptance_ids"])
    all_new_accs=sorted(a for sol in proposed for a in sol["acceptance_ids"])
    if all_old_reqs!=all_new_reqs or all_old_accs!=all_new_accs:
        _deny("REPARTITION_GLOBAL_COVERAGE_DRIFT")
    result={
        "schema_version":"PG04_C6_REPARTITION_PROPOSAL_V1",
        "status":"CANDIDATE_NOT_ADMITTED",
        "source_partition_sha256":psha,
        "pg07_repair_edge_sha256":edge_sha,
        "original_solution_id":target_id,
        "candidate_solution_ids":sorted(new_ids),
        "jit_attempt_disposition":split_plan["jit_attempt_disposition"],
        "separation_evidence_ref":split_plan["separation_evidence_ref"],
        "downstream_rebound_conservatively":sorted(downstream),
        "proposed_solutions":sorted(proposed,key=lambda x:x["id"]),
        "coverage_preserved":{"requirements":len(all_new_reqs),"acceptances":len(all_new_accs),
                              "atoms":len(atoms)},
        "dependency_dag_validated":True,
        "semantic_boundary_verified":False,
        "budget_readback_attested":False,
        "pg07_remeasurement_executed":False,
        "independent_judge_executed":False,
        "material_truncation_allowed":False,
        "production_authority":False,"handoff_allowed":False,
        "next_gate":"INDEPENDENT_SEMANTIC_REVIEW_THEN_PG07_CURRENT_REMEASUREMENT",
    }
    result["candidate_sha256"]=_hash(result)
    return result
