"""PG-03_C8 -> PG-04 candidate handoff guard.

Reuses PROGRAMMING_SOLUTION_PARTITION_CONTRACT_V1 (PR #1912).
Never grants dispatch, PG-04 admission, or ledger closure.
"""
from collections.abc import Mapping
import hashlib
import json

class HandoffBlocked(ValueError):
    pass

def _identifiers(value, label):
    if not isinstance(value,list) or not value or any(not isinstance(x,str) or not x.strip() for x in value) or len(set(value))!=len(value):
        raise HandoffBlocked(label+"_INVALID")
    return set(value)

def prepare_pg04_handoff(*, strategy, sufficiency, exceptions_result, partition_contract, solution_coverage, assurance_receipt=None):
    if not isinstance(strategy,Mapping) or strategy.get("status")!="CANDIDATE_NOT_ADMITTED" or strategy.get("production_authority") is not False or strategy.get("handoff_allowed") is not False:
        raise HandoffBlocked("STRATEGY_NOT_ADMITTED")
    requirements=_identifiers(strategy.get("requirement_ids"),"REQUIREMENTS")
    acceptance=_identifiers(strategy.get("acceptance_ids"),"ACCEPTANCE")
    scopes=_identifiers(strategy.get("scope_ids"),"SCOPES")
    if not isinstance(sufficiency,Mapping) or sufficiency.get("status")!="CANDIDATE_SUFFICIENT_NOT_ADMITTED" or sufficiency.get("production_authority") is not False or sufficiency.get("handoff_allowed") is not False or sufficiency.get("gaps")!=[]:
        raise HandoffBlocked("SUFFICIENCY_NOT_ESTABLISHED")
    if sufficiency.get("source_strategy_sha256")!=strategy.get("candidate_sha256") or not isinstance(strategy.get("candidate_sha256"),str) or not strategy["candidate_sha256"]:
        raise HandoffBlocked("STRATEGY_SUFFICIENCY_BINDING_MISSING")
    if not isinstance(exceptions_result,Mapping) or exceptions_result.get("status")!="CANDIDATE_NOT_ADMITTED" or exceptions_result.get("production_authority") is not False or exceptions_result.get("waiver_authorized") is not False or exceptions_result.get("handoff_allowed") is not False or exceptions_result.get("exceptions")!=[]:
        raise HandoffBlocked("UNRESOLVED_EXCEPTIONS")
    if not isinstance(partition_contract,Mapping) or partition_contract.get("schema_version")!="PROGRAMMING_SOLUTION_PARTITION_CONTRACT_V1":
        raise HandoffBlocked("PARTITION_CONTRACT_INVALID")
    policy=partition_contract.get("partition_policy",{})
    coverage=partition_contract.get("coverage",{})
    if not isinstance(policy,Mapping) or not isinstance(coverage,Mapping) or policy.get("canonical_spec_count")!=1 or policy.get("partition_unit")!="SOLUTION" or policy.get("minimum_rule")!="SMALLEST_COHERENT_VALID_CHANGE" or coverage.get("material_requirement_coverage_required_percent")!=100 or coverage.get("acceptance_obligation_coverage_required_percent")!=100:
        raise HandoffBlocked("PARTITION_POLICY_DRIFT")
    if not isinstance(solution_coverage,list) or not solution_coverage:
        raise HandoffBlocked("SOLUTIONS_MISSING")
    seen=set()
    req_owners={}
    acc_owners={}
    for row in solution_coverage:
        if not isinstance(row,Mapping):
            raise HandoffBlocked("SOLUTION_INVALID")
        identifier=row.get("solution_id")
        if not isinstance(identifier,str) or not identifier.strip() or identifier in seen:
            raise HandoffBlocked("SOLUTION_ID_INVALID")
        seen.add(identifier)
        if not isinstance(row.get("strategy_ref"),str) or not row["strategy_ref"].strip():
            raise HandoffBlocked("PARTITION_STRATEGY_REF_MISSING")
        row_scopes=_identifiers(row.get("scope_ids"),"SOLUTION_SCOPES")
        if not row_scopes.issubset(scopes):
            raise HandoffBlocked("UNCLASSIFIED_SCOPE")
        for key,owners in (("requirement_ids",req_owners),("acceptance_ids",acc_owners)):
            for item in _identifiers(row.get(key),key.upper()):
                if item in owners:
                    raise HandoffBlocked("DUPLICATE_OWNERSHIP")
                owners[item]=identifier
        depends=row.get("depends_on",[])
        if not isinstance(depends,list) or any(not isinstance(x,str) or not x.strip() for x in depends) or len(set(depends))!=len(depends) or identifier in depends:
            raise HandoffBlocked("DEPENDENCIES_INVALID")
    if set(req_owners)!=requirements or set(acc_owners)!=acceptance:
        raise HandoffBlocked("MATERIAL_COVERAGE_INCOMPLETE_OR_FOREIGN")
    for row in solution_coverage:
        if any(dep not in seen for dep in row.get("depends_on",[])):
            raise HandoffBlocked("DEPENDENCY_UNKNOWN")
    dependencies={row["solution_id"]:row.get("depends_on",[]) for row in solution_coverage}
    visited=set()
    visiting=set()
    def visit(node):
        if node in visiting:
            raise HandoffBlocked("DEPENDENCY_CYCLE")
        if node in visited:
            return
        visiting.add(node)
        for dep in dependencies[node]:
            visit(dep)
        visiting.remove(node)
        visited.add(node)
    for node in sorted(dependencies):
        visit(node)
    # Any received assurance receipt is untrusted until verified by the existing
    # independent reviewer/ledger; this candidate never uses it to grant authority.
    payload={"schema_version":"PG03_C8_PG04_HANDOFF_CANDIDATE_V1",
        "status":"CANDIDATE_NOT_ADMITTED","production_authority":False,
        "dispatch_allowed":False,"handoff_allowed":False,
        "strategy_sha256":strategy["candidate_sha256"],
        "partition_contract_schema":partition_contract["schema_version"],
        "requirement_owners":dict(sorted(req_owners.items())),
        "acceptance_owners":dict(sorted(acc_owners.items())),
        "solution_dependencies":dict(sorted(dependencies.items())),
        "assurance_state":"UNVERIFIED_EXTERNAL_AUTHORITY",
        "reason":"PG04_ADMISSION_AND_INDEPENDENT_ASSURANCE_REQUIRED"}
    payload["candidate_sha256"]=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    return payload
