"""PG-03_C8 -> PG-04 partition adapter; no dispatcher, judge or authority.

Accept ONLY the typed PG03_C8_PG04_HANDOFF_CANDIDATE_V1 envelope.
PG04 still needs caller-supplied typed atoms/outcomes; no A9 authenticity claimed.
"""
import hashlib
import json
from .pg04_semantic_partition_candidate_v1 import partition_by_semantic_outcome

class BridgeBlocked(ValueError):
    pass

def _digest(value):
    return hashlib.sha256(json.dumps(
        value,sort_keys=True,separators=(",",":"),ensure_ascii=True
    ).encode("utf-8")).hexdigest()

def _blocked(code):
    raise BridgeBlocked(code)

def partition_from_pg03_c8(*, pg03_handoff, strategy, partition_contract,
                           obligations, outcome_registry):
    if (not isinstance(pg03_handoff,dict) or
        pg03_handoff.get("schema_version")!="PG03_C8_PG04_HANDOFF_CANDIDATE_V1"):
        _blocked("PG04_PG03_C8_HANDOFF_REQUIRED")
    sha=pg03_handoff.get("candidate_sha256")
    if sha!=_digest({k:v for k,v in pg03_handoff.items() if k!="candidate_sha256"}):
        _blocked("PG04_PG03_C8_DIGEST_DRIFT")
    if (pg03_handoff.get("status")!="CANDIDATE_NOT_ADMITTED" or
        any(pg03_handoff.get(k) is not False for k in (
            "production_authority","handoff_allowed","dispatch_allowed"))):
        _blocked("PG04_PG03_C8_AUTHORITY_INVALID")
    if (not isinstance(strategy,dict) or
        pg03_handoff.get("strategy_sha256")!=strategy.get("candidate_sha256")):
        _blocked("PG04_STRATEGY_HANDOFF_DRIFT")
    if (not isinstance(partition_contract,dict) or
        pg03_handoff.get("partition_contract_schema")!=partition_contract.get("schema_version")):
        _blocked("PG04_PARTITION_CONTRACT_DRIFT")
    req=pg03_handoff.get("requirement_owners")
    acc=pg03_handoff.get("acceptance_owners")
    if not isinstance(req,dict) or not isinstance(acc,dict) or not req or not acc:
        _blocked("PG04_HANDOFF_OWNERS_REQUIRED")
    if set(req)!=set(strategy.get("requirement_ids",[])) or set(acc)!=set(strategy.get("acceptance_ids",[])):
        _blocked("PG04_HANDOFF_COVERAGE_DRIFT")
    pg03_owners=set(req.values())|set(acc.values())
    dependencies=pg03_handoff.get("solution_dependencies")
    if (not isinstance(dependencies,dict) or set(dependencies)!=pg03_owners or
        any(not isinstance(v,list) or any(dep not in pg03_owners for dep in v)
            for v in dependencies.values())):
        _blocked("PG04_HANDOFF_DAG_DRIFT")
    partition=partition_by_semantic_outcome(
        strategy=strategy,partition_contract=partition_contract,
        obligations=obligations,outcome_registry=outcome_registry)
    # The proposed PG-03 allocation must correspond to the PG-04
    # generated semantic solutions. Reject silent split/merge/reassignment.
    pg03_groups={}
    for key,owners in (("requirements",req),("acceptance",acc)):
        for item,owner in owners.items():
            group=pg03_groups.setdefault(owner,{"requirements":set(),"acceptance":set()})
            group[key].add(item)
    actual=set()
    for sol in partition["solutions"]:
        item=(frozenset(sol["requirement_ids"]),frozenset(sol["acceptance_ids"]))
        if item in actual:
            _blocked("PG04_DUPLICATE_SOLUTION_COVERAGE")
        actual.add(item)
    expected={(frozenset(row["requirements"]),frozenset(row["acceptance"])) for row in pg03_groups.values()}
    if actual!=expected:
        _blocked("PG04_PG03_SOLUTION_OWNERSHIP_DRIFT")
    return {
        "schema_version":"PG03_PG04_CONNECTED_PARTITION_CANDIDATE_V1",
        "status":"CANDIDATE_NOT_ADMITTED",
        "source_pg03_c8_sha256":sha,
        "source_pg03_strategy_sha256":strategy["candidate_sha256"],
        "source_pg04_partition_sha256":partition["candidate_sha256"],
        "partition":partition,
        "pg03_pg04_chain_shape_verified":True,
        "pg03_source_authenticated":False,
        "semantic_judge_executed":False,
        "handoff_allowed":False,
        "production_authority":False,
        "dispatch_allowed":False,
    }
