"""PG-03_C3 strategy envelope, candidate only; reuses PG-04 partition policy."""
import hashlib
import json

class StrategyBlocked(ValueError):
    pass

def prepare_strategy(*, classification, stack_evidence, partition_contract, requirement_ids, acceptance_ids, reuse_refs, capability_selector, alternatives, fallback):
    if not isinstance(classification,dict) or classification.get("status")!="CANDIDATE_NOT_ADMITTED":
        raise StrategyBlocked("PG02_CANDIDATE_REQUIRED")
    if classification.get("dispatch_allowed",False):
        raise StrategyBlocked("PG02_AUTHORITY_ESCALATION")
    candidate=classification.get("candidate")
    if not isinstance(candidate,dict) or candidate.get("status")!="CANDIDATE_NOT_ADMITTED":
        raise StrategyBlocked("PG02_CLASSIFICATION_MISSING")
    rows=candidate.get("scopes")
    if not isinstance(rows,list) or not rows or any(not isinstance(r,dict) for r in rows):
        raise StrategyBlocked("SCOPES_INVALID")
    if any(r.get("state")!="READY_FOR_CLASSIFICATION" for r in rows):
        raise StrategyBlocked("NON_READY_SCOPE")
    if not isinstance(stack_evidence,dict) or stack_evidence.get("status")!="CANDIDATE_NOT_ADMITTED" or stack_evidence.get("authority") is not False:
        raise StrategyBlocked("STACK_EVIDENCE_INVALID")
    if not isinstance(stack_evidence.get("commit_sha"),str) or not stack_evidence.get("sources"):
        raise StrategyBlocked("STACK_PROVENANCE_MISSING")
    if not isinstance(partition_contract,dict) or partition_contract.get("schema_version")!="PROGRAMMING_SOLUTION_PARTITION_CONTRACT_V1":
        raise StrategyBlocked("PARTITION_CONTRACT_INVALID")
    policy=partition_contract.get("partition_policy",{})
    cov=partition_contract.get("coverage",{})
    if policy.get("canonical_spec_count")!=1 or policy.get("partition_unit")!="SOLUTION" or policy.get("minimum_rule")!="SMALLEST_COHERENT_VALID_CHANGE" or cov.get("material_requirement_coverage_required_percent")!=100 or cov.get("acceptance_obligation_coverage_required_percent")!=100:
        raise StrategyBlocked("PARTITION_POLICY_DRIFT")
    for value,label in [(requirement_ids,"REQUIREMENTS"),(acceptance_ids,"ACCEPTANCE"),(reuse_refs,"REUSE")]:
        if not isinstance(value,list) or any(not isinstance(x,str) or not x for x in value) or len(set(value))!=len(value):
            raise StrategyBlocked(label+"_INVALID")
    if not requirement_ids or not acceptance_ids:
        raise StrategyBlocked("COVERAGE_NOT_ESTABLISHED")
    if not isinstance(capability_selector,str) or not capability_selector or not isinstance(alternatives,list) or not alternatives or not all(isinstance(x,str) and x for x in alternatives) or not isinstance(fallback,str) or not fallback:
        raise StrategyBlocked("STRATEGY_DECISION_MISSING")
    domains=sorted({d for row in rows for d in row.get("candidate_domains",[])})
    if not domains:
        raise StrategyBlocked("ACTIVE_DOMAINS_MISSING")
    result={"schema_version":"PG03_STRATEGY_CANDIDATE_V1","status":"CANDIDATE_NOT_ADMITTED",
            "dispatch_allowed":False,"production_authority":False,
            "stack_commit_sha":stack_evidence["commit_sha"],"source_sha256":[x["sha256"] for x in stack_evidence["sources"]],
            "scope_ids":sorted(x["scope_id"] for x in rows),"active_domains":domains,
            "capability_selector":capability_selector,"alternatives":alternatives,"fallback":fallback,
            "reuse_refs":sorted(reuse_refs),"requirement_ids":sorted(requirement_ids),
            "acceptance_ids":sorted(acceptance_ids),
            "partition_contract_schema":partition_contract["schema_version"],
            "partition_policy":"SMALLEST_COHERENT_VALID_CHANGE",
            "handoff_allowed":False,"reason":"STRATEGY_CANDIDATE_NOT_ADMITTED_REQUIREMENT_COVERAGE_UNVERIFIED"}
    result["candidate_sha256"]=hashlib.sha256(json.dumps(result,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    return result
