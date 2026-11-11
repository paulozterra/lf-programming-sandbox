"""PG-04_C7 deterministic coverage dossier for the existing INDEPENDENT_ASSURANCE.

Checks source-to-solution ownership, bindings and dependency preservation. Does
not infer semantic fidelity, authenticate A9/PG03/PG04 sources or run a reviewer.
"""
import hashlib
import json

class CoverageDossierBlocked(ValueError):
    pass

def _fail(code):
    raise CoverageDossierBlocked(code)

def _hash(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()

def _ids(value, allow_empty=False):
    return (isinstance(value,list) and (allow_empty or bool(value))
            and all(isinstance(x,str) and bool(x.strip()) for x in value)
            and len(value)==len(set(value)))

def build_coverage_dossier(*,partition,strategy,original_obligations):
    if not isinstance(partition,dict) or partition.get("schema_version")!="PG04_SEMANTIC_PARTITION_CANDIDATE_V1" or partition.get("status")!="CANDIDATE_NOT_ADMITTED" or partition.get("production_authority") is not False or partition.get("handoff_allowed") is not False or partition.get("source_authenticity")!="UNVERIFIED":
        _fail("PARTITION_NOT_UNTRUSTED_CANDIDATE")
    part_sha=partition.get("candidate_sha256")
    if not isinstance(part_sha,str) or part_sha!=_hash({k:v for k,v in partition.items() if k!="candidate_sha256"}):
        _fail("PARTITION_DIGEST_DRIFT")
    if not isinstance(strategy,dict) or strategy.get("status")!="CANDIDATE_NOT_ADMITTED" or strategy.get("production_authority") is not False:
        _fail("STRATEGY_NOT_CANDIDATE")
    strategy_sha=strategy.get("candidate_sha256")
    if not isinstance(strategy_sha,str) or strategy_sha!=_hash({k:v for k,v in strategy.items() if k!="candidate_sha256"}) or partition.get("strategy_sha256")!=strategy_sha:
        _fail("STRATEGY_BINDING_DRIFT")
    expected_req=strategy.get("requirement_ids")
    expected_acc=strategy.get("acceptance_ids")
    expected_scopes=strategy.get("scope_ids")
    if not all(_ids(v) for v in (expected_req,expected_acc,expected_scopes)):
        _fail("STRATEGY_MATERIAL_SETS_INVALID")
    if not isinstance(original_obligations,list) or not original_obligations:
        _fail("ORIGINAL_OBLIGATIONS_MISSING")
    atom_by_id={}
    atom_req={}
    atom_acc={}
    for atom in original_obligations:
        if not isinstance(atom,dict) or not isinstance(atom.get("atom_id"),str) or not atom["atom_id"].strip() or atom["atom_id"] in atom_by_id:
            _fail("ORIGINAL_ATOM_ID_INVALID")
        if atom.get("scope_id") not in expected_scopes or not _ids(atom.get("requirement_ids"),True) or not _ids(atom.get("acceptance_ids"),True) or not (atom["requirement_ids"] or atom["acceptance_ids"]):
            _fail("ORIGINAL_ATOM_MATERIAL_INVALID")
        aid=atom["atom_id"]
        atom_by_id[aid]=atom
        for kind, ids, index in (("REQUIREMENT",atom["requirement_ids"],atom_req),("ACCEPTANCE",atom["acceptance_ids"],atom_acc)):
            for value in ids:
                if value in index:_fail("ORIGINAL_MATERIAL_DUPLICATE")
                index[value]=aid
    if set(atom_req)!=set(expected_req) or set(atom_acc)!=set(expected_acc):
        _fail("ORIGINAL_MATERIAL_STRATEGY_DRIFT")
    sols=partition.get("solutions")
    if not isinstance(sols,list) or not sols:
        _fail("SOLUTIONS_MISSING")
    owners={}
    solution_index={}
    req_solution={}
    acc_solution={}
    for sol in sols:
        if not isinstance(sol,dict) or not isinstance(sol.get("id"),str) or not sol["id"].strip() or sol["id"] in solution_index or sol.get("strategy_ref")!=strategy_sha:
            _fail("SOLUTION_ID_OR_STRATEGY_INVALID")
        sid=sol["id"]
        solution_index[sid]=sol
        refs=sol.get("source_bindings")
        ids=sol.get("atom_ids")
        if not _ids(ids) or not isinstance(refs,list) or len(refs)!=len(ids):
            _fail("SOLUTION_ATOM_BINDINGS_INCOMPLETE")
        binding_ids=[]
        expected_r=set()
        expected_a=set()
        expected_sc=set()
        expected_shared=set()
        expected_write=set()
        for aid in ids:
            if aid not in atom_by_id:_fail("FOREIGN_ATOM_IN_SOLUTION")
            if aid in owners:_fail("ATOM_MULTIPLE_SOLUTION_OWNERS")
            owners[aid]=sid
            atom=atom_by_id[aid]
            expected_r.update(atom["requirement_ids"])
            expected_a.update(atom["acceptance_ids"])
            expected_sc.add(atom["scope_id"])
            expected_shared.update(atom.get("shared_contract_refs",[]))
            expected_write.update(atom.get("write_scope",[]))
        for ref in refs:
            if not isinstance(ref,dict) or ref.get("atom_id") not in ids or ref["atom_id"] in binding_ids:
                _fail("SOURCE_BINDING_INVALID")
            aid=ref["atom_id"]
            binding_ids.append(aid)
            atom=atom_by_id[aid]
            fields=("source_ref","scope_id","risk_level","semantic_rationale","write_scope_reason","implementation_state")
            if any(ref.get(field)!=atom.get(field) for field in fields):
                _fail("ATOM_SOURCE_BINDING_DRIFT")
            state=atom["implementation_state"]
            if state=="EXISTING":
                evidence=("as_is_ref","delta_ref")
                incompatible=("bounded_reuse_assessment_ref",)
            elif state=="NEW":
                evidence=("bounded_reuse_assessment_ref",)
                incompatible=("as_is_ref","delta_ref")
            else:_fail("ATOM_IMPLEMENTATION_STATE_INVALID")
            if (any(not isinstance(atom.get(field),str) or not atom[field].strip() or ref.get(field)!=atom[field] for field in evidence)
                or any(field in ref or field in atom for field in incompatible)):
                _fail("ATOM_IMPLEMENTATION_EVIDENCE_DRIFT")
        if set(binding_ids)!=set(ids):
            _fail("SOURCE_BINDING_INVALID")
        if (not _ids(sol.get("requirement_ids"),True) or not _ids(sol.get("acceptance_ids"),True)
            or set(sol["requirement_ids"])!=expected_r or set(sol["acceptance_ids"])!=expected_a
            or not _ids(sol.get("write_scope")) or set(sol["write_scope"])!=expected_write
            or not _ids(sol.get("shared_contract_refs"),True) or set(sol["shared_contract_refs"])!=expected_shared):
            _fail("SOLUTION_COVERAGE_OR_SCOPE_DRIFT")
        for req in expected_r:
            if req in req_solution:_fail("DUPLICATE_REQUIREMENT_OWNERSHIP")
            req_solution[req]=sid
        for acc in expected_a:
            if acc in acc_solution:_fail("DUPLICATE_ACCEPTANCE_OWNERSHIP")
            acc_solution[acc]=sid
    if set(owners)!=set(atom_by_id) or set(req_solution)!=set(expected_req) or set(acc_solution)!=set(expected_acc):
        _fail("COVERAGE_INCOMPLETE")
    graph={}
    for sid,sol in solution_index.items():
        deps=sol.get("depends_on")
        if not _ids(deps,True) or sid in deps or any(dep not in solution_index for dep in deps):
            _fail("SOLUTION_DEPENDENCY_INVALID")
        graph[sid]=deps
    active=set()
    visited=set()
    def visit(sid):
        if sid in active:_fail("SOLUTION_DEPENDENCY_CYCLE")
        if sid in visited:return
        active.add(sid)
        for dep in graph[sid]:visit(dep)
        active.remove(sid)
        visited.add(sid)
    for sid in graph:visit(sid)
    for aid,atom in atom_by_id.items():
        sid=owners[aid]
        for linked in atom.get("coimplement_with",[]):
            if linked not in owners or owners[linked]!=sid:
                _fail("COIMPLEMENT_SPLIT_ACROSS_SOLUTIONS")
        for dep in atom.get("depends_on",[]):
            if dep not in owners:
                _fail("ATOM_DEPENDENCY_UNKNOWN")
            dep_sid=owners[dep]
            if dep_sid!=sid and dep_sid not in graph[sid]:
                _fail("ATOM_DEPENDENCY_NOT_PROJECTED")
    rows=[]
    for sid in sorted(solution_index):
        sol=solution_index[sid]
        rows.append({
            "solution_id":sid,
            "atom_ids":sorted(sol["atom_ids"]),
            "requirement_ids":sorted(sol["requirement_ids"]),
            "acceptance_ids":sorted(sol["acceptance_ids"]),
            "depends_on":sorted(graph[sid]),
            "source_bindings_count":len(sol["source_bindings"]),
        })
    dossier={
        "schema_version":"PG04_C7_DETERMINISTIC_COVERAGE_DOSSIER_V1",
        "status":"CANDIDATE_NOT_ADMITTED",
        "partition_sha256":part_sha,
        "strategy_sha256":strategy_sha,
        "original_obligations_sha256":_hash(original_obligations),
        "bidirectional_requirement_coverage":"STRUCTURALLY_COMPLETE",
        "bidirectional_acceptance_coverage":"STRUCTURALLY_COMPLETE",
        "coverage":{"atoms":len(owners),"requirements":len(req_solution),"acceptances":len(acc_solution)},
        "solutions":rows,
        "coverage_deterministic_check":"PASS_SOURCE_ONLY",
        "semantic_fidelity_judged":False,
        "source_currentness_attested":False,
        "independent_review_executed":False,
        "ledger_subject_receipt_verified":False,
        "production_authority":False,
        "handoff_allowed":False,
        "next_gate":"EXISTING_INDEPENDENT_ASSURANCE_CURRENT_SUBJECT_REVIEW"
    }
    dossier["candidate_sha256"]=_hash(dossier)
    return dossier
