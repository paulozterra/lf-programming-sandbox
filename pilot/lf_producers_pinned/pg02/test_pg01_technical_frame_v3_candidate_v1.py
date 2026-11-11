import copy
from pg01_technical_frame_v3_candidate_v1 import CONTRACT,preflight
bind={k:"v" for k in CONTRACT["frame_binding"]}
bind["context_sha256"]="a"*64;bind["binding_key_sha256"]="b"*64
rows={k:{"source_ref":"fixture","source_digest_sha256":"c"*64,"authority_receipt_ref":"fixture",
"verified_by":"INDEPENDENT_TRUSTED_READBACK","currentness":"CURRENT",
"target_repo":bind["target_repo"],"target_head_sha":bind["target_head_sha"]} for k in CONTRACT["required_evidence"]}
assert preflight(bind,rows)["reason"]=="PG01_V3_PROVENANCE_UNAVAILABLE"
for name in CONTRACT["required_evidence"]:
 x=copy.deepcopy(rows);x.pop(name)
 assert preflight(bind,x)=={"verified":False,"reason":"PG01_V3_EVIDENCE_MISSING","evidence":name}
for name,field,value,reason in [
 ("l3_manifest","source_digest_sha256","x","PG01_V3_EVIDENCE_NOT_VERIFIED"),
 ("d15_architecture","target_head_sha","drift","PG01_V3_TARGET_DRIFT"),
 ("control_qualification","verified_by","CALLER_VERIFIED","PG01_V3_EVIDENCE_NOT_VERIFIED"),
 ("standards_catalog_version","currentness","STALE","PG01_V3_EVIDENCE_NOT_VERIFIED")]:
 x=copy.deepcopy(rows);x[name][field]=value
 assert preflight(bind,x)["reason"]==reason
assert preflight({**bind,"context_sha256":"x"},rows)["verified"] is False
assert preflight(bind,rows)["verified"] is False
print("PG01_V3_PREFLIGHT_FAIL_CLOSED_PASS six_missing=6 adversarial=5 no_authorization=True")
