"""Typed PG-02 boundary outcome, not an executable Analysis dispatch."""
from pg02_classifier_v1 import classify, PG02Blocked

def classify_with_outcome(snapshot, mapping, *, pg01_binding=None):
    try:
        candidate=classify(snapshot,mapping,pg01_binding=pg01_binding)
    except PG02Blocked as e:
        code=str(e)
        reason=code.split(":",1)[-1]
        if code.startswith("CONTRADICTION:"):
            return {"decision":"CONTRADICTION","return_to":"ANALYSIS_PHASE_1",
                    "dispatch_allowed":False,"reason_code":reason,"status":"BLOCKED"}
        return {"decision":"BLOCK","return_to":None,"dispatch_allowed":False,
                "reason_code":code,"status":"BLOCKED"}
    return {"decision":"CANDIDATE_ONLY","return_to":None,
            "dispatch_allowed":False,"status":"CANDIDATE_NOT_ADMITTED","candidate":candidate}
