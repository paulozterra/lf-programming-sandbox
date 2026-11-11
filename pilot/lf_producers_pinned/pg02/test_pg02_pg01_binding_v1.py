"""PG-02 M3/M6 provenance contract tests: candidate-only, no authenticated runtime authority."""
import copy
from test_pg02_classifier_v1 import s,m,pg01_binding
from pg02_classifier_v1 import classify,PG02Blocked

def blocked(binding,expected):
    try: classify(s,m,pg01_binding=binding)
    except PG02Blocked as ex: assert str(ex)==expected,(str(ex),expected)
    else: raise AssertionError("unexpected admission")
blocked(None,"MISSING:PG01_C4_FRAMEWORK_REQUIRED")
b=copy.deepcopy(pg01_binding);b["source"]="CALLER_CLAIM"
blocked(b,"MISSING:PG01_C4_FRAMEWORK_REQUIRED")
b=copy.deepcopy(pg01_binding);b.pop("architecture_commit")
blocked(b,"MISSING:PG01_C4_FRAMEWORK_INCOMPLETE")
b=copy.deepcopy(pg01_binding);b["architecture_profile"]={}
blocked(b,"MISSING:PG01_C4_ARCHITECTURE_LAYERS")
b=copy.deepcopy(pg01_binding);b.pop("context_binding")
blocked(b,"MISSING:PG01_CONTEXT_RECEIPT_BINDING")
b=copy.deepcopy(pg01_binding);b["context_binding"]["context_sha256"]="not-a-pg-hash"
blocked(b,"CONTRADICTION:PG01_CONTEXT_DIGEST_INVALID")
result=classify(s,m,pg01_binding=pg01_binding)
assert result["status"]=="CANDIDATE_NOT_ADMITTED"
assert result["context_sha256"]==pg01_binding["context_binding"]["context_sha256"]
assert result["pg01_receipt_ref"]==pg01_binding["context_binding"]["receipt_ref"]
assert result["source_digest_note"]=="PYTHON_JSON_ONLY_NOT_PG01_HASH"
print("PG02_M3_M6_BOUNDARY_PASS negatives=6 candidate_not_admitted=True")
