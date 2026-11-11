"""Read-only PG-03 subject envelope preflight for existing Independent Assurance v3."""
import re
import uuid
SHA=re.compile(r"^[0-9a-f]{64}$")
HEAD=re.compile(r"^[0-9a-f]{40}$")
def preflight_pg03_subject(data):
    required=("subject_type","subject_ref","subject_sha256","source_head_sha","subject_receipt_id",
              "producer_execution_id","reviewer_execution_id","review_required","required_dimensions",
              "dispatch_receipt_id","request_sha256","plan_digest","capability_manifest_sha256")
    if not isinstance(data,dict) or any(not data.get(k) for k in required):
        return {"status":"BLOCKED","code":"SUBJECT_ENVELOPE_INCOMPLETE","authority":False}
    if data["subject_type"]!="PG03_TECHNICAL_STRATEGY":
        return {"status":"BLOCKED","code":"PG03_SUBJECT_TYPE_MISMATCH","authority":False}
    if not SHA.fullmatch(str(data["subject_sha256"])) or not SHA.fullmatch(str(data["request_sha256"])) or not SHA.fullmatch(str(data["capability_manifest_sha256"])) or not HEAD.fullmatch(str(data["source_head_sha"])):
        return {"status":"BLOCKED","code":"DIGEST_FORMAT_INVALID","authority":False}
    for field in ("subject_receipt_id","dispatch_receipt_id"):
        try:
            parsed=uuid.UUID(str(data[field]))
        except (TypeError,ValueError,AttributeError):
            return {"status":"BLOCKED","code":"RECEIPT_UUID_INVALID","authority":False}
        if str(parsed)!=str(data[field]).lower():
            return {"status":"BLOCKED","code":"RECEIPT_UUID_INVALID","authority":False}
    if data["subject_receipt_id"]==data["dispatch_receipt_id"]:
        return {"status":"BLOCKED","code":"RECEIPT_ID_COLLISION","authority":False}
    if data["producer_execution_id"]==data["reviewer_execution_id"]:
        return {"status":"BLOCKED","code":"REVIEWER_NOT_INDEPENDENT","authority":False}
    if data["review_required"] is not True or not isinstance(data["required_dimensions"],list) or not data["required_dimensions"] or any(not isinstance(x,str) or not x.strip() for x in data["required_dimensions"]) or len(set(data["required_dimensions"]))!=len(data["required_dimensions"]):
        return {"status":"BLOCKED","code":"REVIEW_DIMENSIONS_INVALID","authority":False}
    return {"status":"CANDIDATE_NOT_ADMITTED","code":"EXTERNAL_RECEIPT_READBACK_REQUIRED","authority":False,
            "operation_code":"REVISION_INDEPENDIENTE_ESTRATEGIA_LF",
            "capability_code":"INDEPENDENT_ASSURANCE","runtime_call_permitted":False}
