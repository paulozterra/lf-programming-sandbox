#!/usr/bin/env python3
"""PG-02_C5 external-fixture sample judge (source-only, no production authority).

The sampling oracle and expectations are defined here without importing any
producer test, classifier fixture, domain mapper or output-hash implementation.
Only the public candidate entrypoints are invoked as subjects under test.
"""
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pg02"))
from pg02_classifier_v1 import classify, PG02Blocked
from pg02_classification_outcome_v1 import classify_with_outcome

def fixture():
    """Independently constructed miniature A2 + A7 + C4 sample."""
    snap = {
        "schema_version": "PROGRAMMING_CONTEXT_SNAPSHOT_V1",
        "target_granularity": {"level": "SCREEN", "target_ref": "SCREEN-SAMPLE-01"},
        "scope_readiness": [
            {"scope_id": "ALPHA", "status": "READY", "material_front_refs": ["FR-UI"]},
            {"scope_id": "BETA", "status": "READY", "material_front_refs": ["FR-API"]},
        ],
        "material_front_coverage": {
            "all_material_fronts_accounted": True,
            "unmapped_material_signals": [],
            "material_fronts": [
                {"front_id": "FR-UI", "front_kind": "UI_VISUAL", "status": "REQUIRED",
                 "closure": "CLOSED", "scope_refs": ["ALPHA"]},
                {"front_id": "FR-API", "front_kind": "API_CONTRACT", "status": "REQUIRED",
                 "closure": "CLOSED", "scope_refs": ["BETA"]},
            ],
        },
        "scope_front_matrix": [
            {"scope_id": "ALPHA", "front_id": "FR-UI", "front_status": "REQUIRED",
             "front_closure": "CLOSED", "effect_on_scope": "PRESERVE"},
            {"scope_id": "BETA", "front_id": "FR-API", "front_status": "REQUIRED",
             "front_closure": "CLOSED", "effect_on_scope": "PRESERVE"},
        ],
    }
    catalog = {
        "state": "SOURCE_ONLY_CANDIDATE",
        "source_ref": "fixture://independent-c5",
        "front_kind_domains": {
            "UI_VISUAL": ["STD-FE", "NAV", "MSG"],
            "API_CONTRACT": ["STD-API", "SEC"],
        },
        "domain_stack_layers": {
            "STD-FE": ["FRONTEND"], "NAV": ["FRONTEND"], "MSG": ["FRONTEND"],
            "STD-API": ["BACKEND"], "SEC": ["BACKEND"],
        },
    }
    binding = {
        "source": "PG01_C4",
        "architecture_repo": "fixture/product",
        "architecture_commit": "f"*40,
        "manifest_digest_sha256": "a"*64,
        "architecture_profile": {"active_layers": ["FRONTEND"]},
        "context_binding": {
            "context_id": "fixture://A9/context",
            "context_sha256": "b"*64,
            "receipt_ref": "fixture://PG01/receipt",
        },
    }
    return snap, catalog, binding

def independent_expected(layers):
    """Frozen sample truth table, not derived from classification output."""
    if layers == ["FRONTEND"]:
        return {"ALPHA": ("READY_FOR_CLASSIFICATION", ("MSG", "NAV", "STD-FE")),
                "BETA": ("BLOCKED", ())}
    if layers == ["BACKEND"]:
        return {"ALPHA": ("BLOCKED", ()),
                "BETA": ("READY_FOR_CLASSIFICATION", ("SEC", "STD-API"))}
    if layers == ["FRONTEND", "BACKEND"]:
        return {"ALPHA": ("READY_FOR_CLASSIFICATION", ("MSG", "NAV", "STD-FE")),
                "BETA": ("READY_FOR_CLASSIFICATION", ("SEC", "STD-API"))}
    raise AssertionError("Undeclared layer profile in frozen oracle")

s, m, b = fixture()
positive_cases = 0
for layers in (["FRONTEND"], ["BACKEND"], ["FRONTEND", "BACKEND"]):
    binding = copy.deepcopy(b)
    binding["architecture_profile"]["active_layers"] = layers
    inputs_before = copy.deepcopy((s, m, binding))
    result = classify(s, m, pg01_binding=binding)
    rows = {r["scope_id"]: (r["state"], tuple(r["candidate_domains"])) for r in result["scopes"]}
    assert rows == independent_expected(layers), (layers, rows)
    assert result["status"] == "CANDIDATE_NOT_ADMITTED"
    assert result["source_digest_note"] == "PYTHON_JSON_ONLY_NOT_PG01_HASH"
    assert result["context_sha256"] == "b"*64
    assert result == classify(copy.deepcopy(s), copy.deepcopy(m), pg01_binding=copy.deepcopy(binding))
    assert (s, m, binding) == inputs_before
    out = classify_with_outcome(s, m, pg01_binding=binding)
    assert out["decision"] == "CANDIDATE_ONLY" and out["dispatch_allowed"] is False
    positive_cases += 1

# The fourth sample proves NOT_APPLICABLE never introduces a domain.
na = copy.deepcopy(s)
front = na["material_front_coverage"]["material_fronts"][0]
front["status"] = "NOT_APPLICABLE"
na["scope_front_matrix"][0].update(front_status="NOT_APPLICABLE", effect_on_scope="NOT_APPLICABLE")
na_result = classify(na, m, pg01_binding=b)
na_rows = {r["scope_id"]: r for r in na_result["scopes"]}
assert na_rows["ALPHA"]["candidate_domains"] == []
assert na_rows["ALPHA"]["state"] == "READY_FOR_CLASSIFICATION"
assert na_result["status"] == "CANDIDATE_NOT_ADMITTED"
positive_cases += 1

def negative(label, mutate, code, return_analysis=False):
    snap, mapping, binding = fixture()
    mutate(snap, mapping, binding)
    try:
        classify(snap, mapping, pg01_binding=binding)
    except PG02Blocked as exc:
        assert str(exc) == code, (label, str(exc), code)
    else:
        raise AssertionError(label + " unexpectedly passed")
    out = classify_with_outcome(snap, mapping, pg01_binding=binding)
    assert out["dispatch_allowed"] is False, (label, out)
    if return_analysis:
        assert out["decision"] == "CONTRADICTION"
        assert out["return_to"] == "ANALYSIS_PHASE_1"
    else:
        assert out["decision"] == "BLOCK"
    print("PG02_C5_INDEPENDENT_NEGATIVE_PASS=" + label)

negative("a2_missing", lambda s,m,b:s.pop("target_granularity"), "CONTRADICTION:A2_MISSING", True)
negative("a7_front_parity", lambda s,m,b:s["scope_front_matrix"][0].update(front_closure="BLOCKED"), "CONTRADICTION:A7_PARITY", True)
negative("unmapped_material", lambda s,m,b:s["material_front_coverage"].update(unmapped_material_signals=["UNKNOWN"]), "CONTRADICTION:A7_UNACCOUNTED_MATERIAL_SIGNAL", True)
negative("framework_missing", lambda s,m,b:b.update(source="CALLER"), "MISSING:PG01_C4_FRAMEWORK_REQUIRED")
negative("architecture_layers_missing", lambda s,m,b:b.update(architecture_profile={}), "MISSING:PG01_C4_ARCHITECTURE_LAYERS")
negative("catalog_not_authorized", lambda s,m,b:m.update(state="CURRENT_RELEASED"), "CATALOG_NOT_AUTHORIZED")
negative("ready_scope_blocked", lambda s,m,b:(s["material_front_coverage"]["material_fronts"][0].update(closure="BLOCKED"),s["scope_front_matrix"][0].update(front_closure="BLOCKED",effect_on_scope="BLOCKS")), "CONTRADICTION:READY_SCOPE_BLOCKING_FRONT", True)
negative("duplicate_matrix", lambda s,m,b:s["scope_front_matrix"].append(copy.deepcopy(s["scope_front_matrix"][0])), "CONTRADICTION:MATRIX_MISMATCH", True)

print("PASS_PG02_C5_INDEPENDENT_SAMPLE positive=4 negative=8 contradiction_returns=5 "
      "deterministic=true source_unchanged=true dispatch_allowed=false "
      "independent_fixture=true authority=NONE runtime_verified=false")
