from pg03_assurance_envelope_v1 import preflight_pg03_subject
from copy import deepcopy
base={"subject_type":"PG03_TECHNICAL_STRATEGY","subject_ref":"fixture/pg03",
      "subject_sha256":"a"*64,"source_head_sha":"b"*40,"subject_receipt_id":"11111111-1111-4111-8111-111111111111",
      "producer_execution_id":"producer","reviewer_execution_id":"reviewer","review_required":True,
      "required_dimensions":["RULE_FIDELITY","REUSE_CORRECTNESS"],"dispatch_receipt_id":"22222222-2222-4222-8222-222222222222",
      "request_sha256":"c"*64,"plan_digest":"plan-fixture","capability_manifest_sha256":"d"*64}
assert preflight_pg03_subject(base)["status"]=="CANDIDATE_NOT_ADMITTED"
for change,code in (({"subject_receipt_id":None},"SUBJECT_ENVELOPE_INCOMPLETE"),
                    ({"subject_type":"STRATEGY"},"PG03_SUBJECT_TYPE_MISMATCH"),
                    ({"source_head_sha":"bad"},"DIGEST_FORMAT_INVALID"),
                    ({"reviewer_execution_id":"producer"},"REVIEWER_NOT_INDEPENDENT"),
                    ({"required_dimensions":[]},"SUBJECT_ENVELOPE_INCOMPLETE"),
                    ({"review_required":False},"SUBJECT_ENVELOPE_INCOMPLETE")):
    item=deepcopy(base);item.update(change)
    assert preflight_pg03_subject(item)["code"]==code,(change,preflight_pg03_subject(item))
for change,code in (
    ({"subject_receipt_id":"not-uuid"},"RECEIPT_UUID_INVALID"),
    ({"dispatch_receipt_id":base["subject_receipt_id"]},"RECEIPT_ID_COLLISION"),
    ({"required_dimensions":["RULE_FIDELITY",{"bad":1}]},"REVIEW_DIMENSIONS_INVALID"),
    ({"required_dimensions":["RULE_FIDELITY","RULE_FIDELITY"]},"REVIEW_DIMENSIONS_INVALID"),
):
    item=deepcopy(base);item.update(change)
    assert preflight_pg03_subject(item)["code"]==code,(change,preflight_pg03_subject(item))
print("PG03_C9_GENERIC_ASSURANCE_ENVELOPE_PASS positive=1 negative=10 authority=0")
