"""PG-03 semantic-result adapter to existing LF validator; never model authority."""
import importlib.util
from pathlib import Path

def verify_semantic_candidate(*, result, scope_packet, candidate_sha256, scope_sha256, validator_path):
    if not isinstance(candidate_sha256,str) or len(candidate_sha256)!=64 or not isinstance(scope_sha256,str) or len(scope_sha256)!=64:
        return {"status":"BLOCKED","code":"DIGEST_BINDING_MISSING","production_authority":False}
    spec=importlib.util.spec_from_file_location("lf_existing_semantic_validator",str(Path(validator_path)))
    if spec is None or spec.loader is None:
        return {"status":"BLOCKED","code":"VALIDATOR_UNAVAILABLE","production_authority":False}
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    verdict=module.evaluate(result,scope_packet=scope_packet,expected_candidate_sha256=candidate_sha256,expected_scope_packet_sha256=scope_sha256)
    if verdict["status"]!="PASS":
        return {"status":"BLOCKED","code":"EXISTING_SEMANTIC_VALIDATOR_REJECTED",
                "details":verdict["blocking_codes"],"production_authority":False}
    if result.get("verdict")!="PASS_INDEPENDENT_SEMANTIC":
        return {"status":"BLOCKED","code":"SEMANTIC_PASS_VERDICT_REQUIRED","production_authority":False}
    return {"status":"CANDIDATE_NOT_ADMITTED","code":"SEMANTIC_SHAPE_VALID_BUT_ORIGIN_UNATTESTED",
            "production_authority":False,"handoff_allowed":False}
