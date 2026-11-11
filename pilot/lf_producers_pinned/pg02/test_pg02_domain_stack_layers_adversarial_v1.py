"""PG-02 candidate-only fail-closed regression for untrusted domain layer mappings."""
import copy
from test_pg02_classifier_v1 import s, m, pg01_binding
from pg02_classifier_v1 import classify, PG02Blocked

for bad in ([["FRONTEND"]], [{"layer": "FRONTEND"}], ["FRONTEND", "FRONTEND"], ["FRONTEND", ""]):
    mapping = copy.deepcopy(m)
    mapping["domain_stack_layers"]["STD-FE"] = bad
    try:
        classify(copy.deepcopy(s), mapping, pg01_binding=copy.deepcopy(pg01_binding))
    except PG02Blocked as exc:
        assert str(exc) == "CONTRADICTION:DOMAIN_STACK_LAYERS_INVALID:STD-FE", str(exc)
    else:
        raise AssertionError("malformed domain layers were accepted")

assert classify(copy.deepcopy(s), copy.deepcopy(m), pg01_binding=copy.deepcopy(pg01_binding))["status"] == "CANDIDATE_NOT_ADMITTED"
print("PG02_DOMAIN_STACK_LAYER_ADVERSARIAL_PASS negatives=4 positive=1")
