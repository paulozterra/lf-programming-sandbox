"""PG-03_C4 reuse-before-build parity gate, qualification only."""
import hashlib
import json
from pg03_strategy_v1 import StrategyBlocked

def validate_reuse(*, strategy, upstream_reuse, technical_bindings):
    if not isinstance(strategy,dict) or strategy.get("status")!="CANDIDATE_NOT_ADMITTED" or strategy.get("handoff_allowed") is not False:
        raise StrategyBlocked("STRATEGY_NOT_CANDIDATE")
    if not isinstance(upstream_reuse,list) or not isinstance(technical_bindings,list):
        raise StrategyBlocked("REUSE_EVIDENCE_INVALID")
    refs=set()
    required=set()
    for item in upstream_reuse:
        if not isinstance(item,dict) or not isinstance(item.get("ref"),str) or not item["ref"] or item["ref"] in refs:
            raise StrategyBlocked("UPSTREAM_REUSE_INVALID")
        if item.get("decision") not in ("REUSE_AS_IS","EXTEND_EXISTING","NOT_APPLICABLE"):
            raise StrategyBlocked("UPSTREAM_REUSE_INVALID")
        refs.add(item["ref"])
        if item["decision"]=="REUSE_AS_IS":required.add(item["ref"])
    if not required:
        raise StrategyBlocked("UPSTREAM_REUSE_ABSENT")
    if set(strategy.get("reuse_refs",[]))!=required:
        raise StrategyBlocked("STRATEGY_REUSE_PARITY_MISMATCH")
    bindings={}
    for item in technical_bindings:
        if not isinstance(item,dict) or not isinstance(item.get("ref"),str) or item["ref"] in bindings:
            raise StrategyBlocked("TECHNICAL_BINDING_INVALID")
        if not isinstance(item.get("component"),str) or not item["component"]:
            raise StrategyBlocked("TECHNICAL_BINDING_INVALID")
        if item.get("action") not in ("REUSE_AS_IS","EXTEND_EXISTING"):
            raise StrategyBlocked("TECHNICAL_BINDING_INVALID")
        bindings[item["ref"]]=item
    if set(bindings)!=required:
        raise StrategyBlocked("REUSE_BINDING_COVERAGE_MISMATCH")
    if any(bindings[ref]["action"]!="REUSE_AS_IS" for ref in required):
        raise StrategyBlocked("REUSE_AS_IS_REDEFINITION_FORBIDDEN")
    outcome={"schema_version":"PG03_REUSE_PARITY_CANDIDATE_V1",
             "status":"CANDIDATE_NOT_ADMITTED","dispatch_allowed":False,
             "production_authority":False,"handoff_allowed":False,
             "strategy_sha256":strategy.get("candidate_sha256"),
             "reuse_bindings":[{"ref":ref,"component":bindings[ref]["component"],"action":"REUSE_AS_IS"} for ref in sorted(required)],
             "verification":"STRUCTURAL_PARITY_ONLY_NOT_AUTHENTICATED"}
    outcome["sha256"]=hashlib.sha256(json.dumps(outcome,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    return outcome
