import copy
from pg02_c4_evidence_adapter_v1 import validate_c4_evidence
from pg02_classifier_v1 import PG02Blocked
e={"standards_catalog_version":"STD-candidate","technical_manifest_ref":"git://manifest",
"technical_manifest_sha256":"a"*64,"control_mechanism_ref":"PASE",
"architecture_repo":"fixture://architecture","architecture_commit":"b"*40,
"optimization_mode":"BOUNDED","request_budget_ref":"fixture://budget",
"context_id":"fixture-context","context_sha256":"c"*64,"receipt_ref":"fixture://pg01",
"active_layers":["FRONTEND"]}
b=validate_c4_evidence(e)
assert b["authority_state"]=="UNVERIFIED_CANDIDATE_ONLY"
assert b["context_binding"]["context_id"]==e["context_id"]
for key,bad in [("standards_catalog_version",None),("technical_manifest_ref",None),
("control_mechanism_ref",None),("optimization_mode",None),("request_budget_ref",None),
("technical_manifest_sha256","bad"),("architecture_commit","bad"),("context_sha256","bad"),
("active_layers",[])]:
 x=copy.deepcopy(e);x[key]=bad
 try:validate_c4_evidence(x)
 except PG02Blocked:pass
 else:raise AssertionError(key)
print("PG01_C4_CANDIDATE_ADAPTER_PASS negatives=9 authority=UNVERIFIED")
