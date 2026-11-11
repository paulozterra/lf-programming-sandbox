import copy
from test_pg02_classifier_v1 import s,m,pg01_binding
from pg02_classifier_v1 import classify, PG02Blocked
from pg02_classification_outcome_v1 import classify_with_outcome
def reject(snap,reason):
    try: classify(snap,m,pg01_binding=pg01_binding)
    except PG02Blocked as ex: assert str(ex)==reason,(str(ex),reason)
    else: raise AssertionError("Unexpected classification: "+reason)
ghost=copy.deepcopy(s)
ghost["material_front_coverage"]["material_fronts"][0]["scope_refs"].append("GHOST")
ghost["scope_front_matrix"].append({"scope_id":"GHOST","front_id":"F1","front_status":"REQUIRED","front_closure":"CLOSED","effect_on_scope":"PRESERVE"})
reject(ghost,"CONTRADICTION:A7_UNKNOWN_SCOPE")
for value in (None,[],42,"bad"):
    reject(value,"CONTRADICTION:INVALID_SHAPE")
    assert classify_with_outcome(value,m,pg01_binding=pg01_binding)["decision"]=="CONTRADICTION"
missing=copy.deepcopy(s)
del missing["material_front_coverage"]["material_fronts"][0]["scope_refs"]
reject(missing,"CONTRADICTION:INVALID_SHAPE")
wrong=copy.deepcopy(s)
wrong["scope_readiness"][0]["status"]="WHATEVER"
reject(wrong,"CONTRADICTION:READINESS_INVALID")
blocked=copy.deepcopy(s)
blocked["material_front_coverage"]["material_fronts"][0]["closure"]="BLOCKED"
blocked["scope_front_matrix"][0]["front_closure"]="BLOCKED"
blocked["scope_front_matrix"][0]["effect_on_scope"]="BLOCKS"
reject(blocked,"CONTRADICTION:READY_SCOPE_BLOCKING_FRONT")
closed=copy.deepcopy(s)
closed["scope_front_matrix"][0]["effect_on_scope"]="BLOCKS"
reject(closed,"CONTRADICTION:CLOSED_FRONT_BLOCKS")
orphan=copy.deepcopy(s)
orphan["material_front_coverage"]["material_fronts"].append({"front_id":"F2","front_kind":"UI_VISUAL","status":"OPTIONAL","closure":"CLOSED","scope_refs":["B2B_COPY"]})
reject(orphan,"CONTRADICTION:A7_ENUM")
print("PG02_CLAUDE_H1_M1_M2_M4_L3_PASS cases=10")
