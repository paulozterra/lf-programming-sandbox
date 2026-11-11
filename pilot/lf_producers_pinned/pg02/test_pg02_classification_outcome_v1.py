import copy
from pg02_classification_outcome_v1 import classify_with_outcome
from test_pg02_classifier_v1 import s,m,pg01_binding
ok=classify_with_outcome(s,m,pg01_binding=pg01_binding)
assert ok["decision"]=="CANDIDATE_ONLY" and ok["dispatch_allowed"] is False
broken=copy.deepcopy(s);broken["scope_front_matrix"][0]["front_status"]="OPTIONAL"
out=classify_with_outcome(broken,m,pg01_binding=pg01_binding)
assert out["decision"]=="CONTRADICTION" and out["return_to"]=="ANALYSIS_PHASE_1"
assert out["dispatch_allowed"] is False and out["reason_code"]=="A7_PARITY"
missing=copy.deepcopy(s);missing.pop("target_granularity")
out=classify_with_outcome(missing,m)
assert out["decision"]=="CONTRADICTION" and out["return_to"]=="ANALYSIS_PHASE_1"
assert out["reason_code"]=="A2_MISSING"
print("PG02_OUTCOME_PASS candidate=1 contradiction=1 missing=1")
