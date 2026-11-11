"""Candidate-only PG-01_C4 evidence adapter. Does NOT authenticate caller input.
The trusted readback must be implemented in a governed DB boundary.
"""
import re
from pg02_classifier_v1 import PG02Blocked
HEX64=re.compile(r"^[0-9a-f]{64}$")
COMMIT=re.compile(r"^[0-9a-f]{40}$")
def validate_c4_evidence(evidence):
    if not isinstance(evidence,dict): raise PG02Blocked("MISSING:PG01_C4_EVIDENCE")
    required=("standards_catalog_version","technical_manifest_ref","technical_manifest_sha256",
              "control_mechanism_ref","architecture_repo","architecture_commit",
              "optimization_mode","request_budget_ref","context_id","context_sha256","receipt_ref")
    if any(not isinstance(evidence.get(k),str) or not evidence[k].strip() for k in required):
        raise PG02Blocked("MISSING:PG01_C4_FRAMEWORK_INCOMPLETE")
    if any(not HEX64.fullmatch(evidence[k]) for k in ("technical_manifest_sha256","context_sha256")):
        raise PG02Blocked("CONTRADICTION:PG01_C4_DIGEST_INVALID")
    if not COMMIT.fullmatch(evidence["architecture_commit"]):
        raise PG02Blocked("CONTRADICTION:PG01_C4_ARCHITECTURE_COMMIT_INVALID")
    if not isinstance(evidence.get("active_layers"),list) or not evidence["active_layers"] or any(not isinstance(v,str) or not v for v in evidence["active_layers"]):
        raise PG02Blocked("MISSING:PG01_C4_ARCHITECTURE_LAYERS")
    return {"source":"PG01_C4","architecture_repo":evidence["architecture_repo"],
            "architecture_commit":evidence["architecture_commit"],
            "manifest_digest_sha256":evidence["technical_manifest_sha256"],
            "architecture_profile":{"active_layers":list(evidence["active_layers"])},
            "context_binding":{"context_id":evidence["context_id"],
                               "context_sha256":evidence["context_sha256"],
                               "receipt_ref":evidence["receipt_ref"]},
            "authority_state":"UNVERIFIED_CANDIDATE_ONLY"}
