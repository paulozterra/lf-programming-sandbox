"""General MODIFY rules on synthetic inputs: no real screen, path or rule."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from analysis.host import simulated_admission_gate as gate
from analysis.a9.front_bindings import (FrontBindingGap, MODIFY_NON_BLOCKING_A4_GAPS,
                                        a4_gap_code, modify_scope_from_a4)

T = "SBX-SYNTH"
UNATTESTED = ["SOURCE_READBACK_CURRENTNESS_AND_AUTHORITY_NOT_ATTESTED",
              "TARGET_IMPLEMENTATION_NOT_CONFIRMED"]


def _stages(direct=None, indirect=None, a3_codes=None, a4_codes=None, as_is=True):
    direct = direct if direct is not None else [
        {"depth": 1, "via_relation": "IMPLEMENTED_BY", "affected_ref": "repo://x@" + "a" * 64}]
    a4_codes = a4_codes if a4_codes is not None else UNATTESTED
    return {
        "A1": {}, "A2": {},
        "A3": {"blocking_codes": a3_codes if a3_codes is not None else UNATTESTED,
               "as_is_baseline_or_new_implementation_evidence": {} if as_is else None},
        "A4": {"target_change_action": "MODIFY", "technical_root_ref": "impl://" + T,
               "direct_impacts": direct, "indirect_impacts": indirect or [],
               "unresolved_material_impacts": [{"code": c} for c in a4_codes]},
        "A5": {"blocking_codes": ["A4:" + c for c in a4_codes],
               "material_adr_triggers_true": [], "material_adr_triggers_unknown": [],
               "pending_owner_decisions": []},
    }


@pytest.fixture(autouse=True)
def _target(monkeypatch):
    monkeypatch.setattr(gate, "_target", lambda stages: T)


def test_f2_modify_admits_only_unattested_gaps():
    gate._assess_modify(_stages())


def test_f2_modify_missing_gap_blocks():
    with pytest.raises(gate.AdmissionBlocked, match="F2_A4_BLOCKING_SET_INVALID"):
        gate._assess_modify(_stages(a4_codes=UNATTESTED + ["A4_AS_IS_IMPLEMENTATION_EVIDENCE_MISSING"]))


def test_f2_modify_requires_as_is():
    with pytest.raises(gate.AdmissionBlocked, match="F2_MODIFY_AS_IS_MISSING"):
        gate._assess_modify(_stages(as_is=False))


def test_f2_modify_indirect_impact_blocks():
    with pytest.raises(gate.AdmissionBlocked, match="F2_MODIFY_IMPACT_BEYOND_TARGET"):
        gate._assess_modify(_stages(indirect=[{"depth": 2}]))


def test_f2_modify_only_shared_files_blocks():
    shared = [{"depth": 1, "via_relation": "SHARED_WITH_OTHER_TARGET", "affected_ref": "repo://y@b"}]
    with pytest.raises(gate.AdmissionBlocked, match="F2_MODIFY_IMPACT_BEYOND_TARGET"):
        gate._assess_modify(_stages(direct=shared))


def test_a9_modify_scope_separates_own_and_shared_files():
    a4 = {"target_change_action": "MODIFY", "technical_root_ref": "impl://" + T,
          "direct_impacts": [
              {"via_relation": "IMPLEMENTED_BY", "affected_ref": "repo://own@1"},
              {"via_relation": "SHARED_WITH_OTHER_TARGET", "affected_ref": "repo://shared@2"}]}
    assert modify_scope_from_a4(a4) == {"repo://own@1": "MODIFY_SCOPE",
                                        "repo://shared@2": "CROSS_TARGET_READ_ONLY"}
    assert modify_scope_from_a4({"target_change_action": "CREATE"}) == {}
    with pytest.raises(FrontBindingGap, match="A9_MODIFY_SCOPE_EMPTY"):
        modify_scope_from_a4(dict(a4, direct_impacts=a4["direct_impacts"][1:]))


def test_a9_non_blocking_set_has_no_missing_gap():
    assert all("MISSING" not in c for c in MODIFY_NON_BLOCKING_A4_GAPS)
    assert a4_gap_code("A4:unresolved:CODE_X:S1_A3") == "CODE_X"


def test_a4_modify_projects_excluded_material_items():
    path = Path(__file__).resolve().parents[1] / "programming_analysis/steps/a4/validators/run.py"
    spec = importlib.util.spec_from_file_location("a4_synth", path)
    a4 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(a4)
    a3 = {"schema_version": "TARGETED_EVIDENCE_SET_V1", "business": "LF", "target_ref": T,
          "status": "SOURCE_READBACK_PROCESSED_UNATTESTED", "source_refs": ["s"],
          "material_contract_readback": {"status_items": [
              {"source_ref": "s#ok", "source_status": "VIGENTE"},
              {"source_ref": "s#pending", "source_status": "PENDIENTE"}]}}
    root = "impl://" + T
    rb = {"schema_version": "A4_EXISTING_IMPACT_CORE_READBACK_V1", "business": "LF",
          "target_ref": T, "source_attested": False,
          "inventory_object": {"object_ref": root, "active": True, "object_type": "X",
                               "currentness": "CURRENT"},
          "identity_binding": {"target_ref": T, "inventory_object_ref": root,
                               "source_ref": "s", "source_attested": False},
          "impact_readback": {"source_function": "inventory.fn_impact_analysis_v1",
                              "parameters": {"p_object_ref": root, "p_max_depth": 3,
                                             "p_min_confidence": 0.8},
                              "source_attested": False,
                              "rows": [{"depth": 1, "affected_ref": "repo://f@1",
                                        "affected_type": "F", "via_relation": "IMPLEMENTED_BY",
                                        "min_confidence": 1.0}]},
          "dependency_readback": {"source_function": "inventory.fn_dependencies_v1",
                                  "parameters": {"p_object_ref": root, "p_direction": "BOTH",
                                                 "p_max_depth": 2},
                                  "source_attested": False, "rows": []}}
    out = a4.run(a3, {"schema_version": "ANALYSIS_CHANGE_CLASSIFICATION_V1", "target_ref": T,
                      "change_type": "MODIFY"}, rb)
    assert [x["affected_ref"] for x in out["excluded_pending_obligations"]] == ["s#pending"]


def test_trace_marks_files_registered_by_other_targets_as_shared(tmp_path):
    from analysis.host.request_trace import implementation_evidence
    for name, text in (("own.tsx", "a"), ("shared.tsx", "b")):
        (tmp_path / name).write_text(text)
    sha = lambda n: hashlib.sha256((tmp_path / n).read_bytes()).hexdigest()
    for slug, target in (("req-a", T), ("req-b", "SBX-OTHER")):
        f = tmp_path / "pilot/runs" / slug / "analysis.json"
        f.parent.mkdir(parents=True)
        f.write_text(json.dumps({"request_context": {"target_ref": target}}))
    reg = tmp_path / "pilot/registry/implemented.json"
    reg.parent.mkdir(parents=True)
    reg.write_text(json.dumps({"schema_version": "T7_IMPLEMENTED_REGISTRY_V1", "entries": [
        {"request": "req-a", "area": "FRONTEND", "status": "ATTESTED",
         "files": [{"path": "own.tsx", "sha256": sha("own.tsx")},
                   {"path": "shared.tsx", "sha256": sha("shared.tsx")}]},
        {"request": "req-b", "area": "FRONTEND", "status": "NO_DERIVABLE",
         "files": [{"path": "shared.tsx", "sha256": sha("shared.tsx")}]}]}))
    rows = {r["path"]: r for r in implementation_evidence(tmp_path, T)}
    assert rows["own.tsx"]["shared_with"] == []
    assert rows["shared.tsx"]["shared_with"] == ["SBX-OTHER"]
    assert len(rows["own.tsx"]["blob_sha1"]) == 40
