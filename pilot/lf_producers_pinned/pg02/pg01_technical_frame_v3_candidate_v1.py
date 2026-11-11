"""PG-01 C4/V3 composition candidate. Pure validation, never an authority resolver."""
import hashlib,json,re
from pathlib import Path
CONTRACT=json.loads(Path(__file__).with_name("pg01_technical_frame_v3_candidate_contract.json").read_text())
HEX=re.compile(r"^[0-9a-f]{64}$")
def preflight(binding, evidence):
    if not isinstance(binding,dict) or not isinstance(evidence,dict):
        return {"verified":False,"reason":"PG01_V3_BINDING_INVALID"}
    fields=CONTRACT["frame_binding"]
    if any(not isinstance(binding.get(k),str) or not binding[k] for k in fields):
        return {"verified":False,"reason":"PG01_V3_BINDING_INCOMPLETE"}
    if not HEX.fullmatch(binding["context_sha256"]) or not HEX.fullmatch(binding["binding_key_sha256"]):
        return {"verified":False,"reason":"PG01_V3_CONTEXT_DIGEST_INVALID"}
    for name in CONTRACT["required_evidence"]:
        row=evidence.get(name)
        if not isinstance(row,dict):
            return {"verified":False,"reason":"PG01_V3_EVIDENCE_MISSING","evidence":name}
        if not all(isinstance(row.get(k),str) and row[k] for k in ("source_ref","source_digest_sha256","authority_receipt_ref","verified_by","currentness")):
            return {"verified":False,"reason":"PG01_V3_EVIDENCE_INVALID","evidence":name}
        if not HEX.fullmatch(row["source_digest_sha256"]) or row["currentness"]!="CURRENT" or row["verified_by"]!="INDEPENDENT_TRUSTED_READBACK":
            return {"verified":False,"reason":"PG01_V3_EVIDENCE_NOT_VERIFIED","evidence":name}
        if row.get("target_repo")!=binding["target_repo"] or row.get("target_head_sha")!=binding["target_head_sha"]:
            return {"verified":False,"reason":"PG01_V3_TARGET_DRIFT","evidence":name}
    return {"verified":False,"reason":"PG01_V3_PROVENANCE_UNAVAILABLE",
            "candidate_frame_sha256":hashlib.sha256(json.dumps({"binding":binding,"evidence":evidence},sort_keys=True,separators=(",",":")).encode()).hexdigest(),
            "hash_note":"PYTHON_CANDIDATE_NOT_PG_JSONB_DIGEST"}
