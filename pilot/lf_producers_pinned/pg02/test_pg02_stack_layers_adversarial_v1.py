"""Adversarial PG-02 C2 test. Candidate-only; no PG-01 authority."""
import copy
from pathlib import Path
import runpy
from pg02_classifier_v1 import classify, PG02Blocked

fixture = runpy.run_path(str(Path(__file__).with_name("test_pg02_classifier_v1.py")))
base_snapshot, base_mapping = fixture["s"], fixture["m"]
base_binding = fixture["pg01_binding"]

for bad_layers in ([["FRONTEND"]], [{"name": "FRONTEND"}], ["FRONTEND", "FRONTEND"], ["FRONTEND", ""]):
    binding = copy.deepcopy(base_binding)
    binding["architecture_profile"]["active_layers"] = bad_layers
    try:
        classify(copy.deepcopy(base_snapshot), copy.deepcopy(base_mapping), pg01_binding=binding)
    except PG02Blocked as exc:
        assert str(exc) == "CONTRADICTION:STACK_LAYERS_INVALID", str(exc)
    else:
        raise AssertionError("malformed stack layers were accepted")

assert classify(copy.deepcopy(base_snapshot), copy.deepcopy(base_mapping), pg01_binding=copy.deepcopy(base_binding))["status"] == "CANDIDATE_NOT_ADMITTED"
print("PG02_STACK_LAYER_ADVERSARIAL_PASS negatives=4 positive=1")
