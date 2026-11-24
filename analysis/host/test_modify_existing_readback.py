import importlib.util
from pathlib import Path
import pytest
from analysis.host import fixture_readback_host as host

A4 = Path(__file__).resolve().parents[1] / "programming_analysis/steps/a4/validators/run.py"
T = "SBX-SYNTH"


def _a4():
    spec = importlib.util.spec_from_file_location("a4_run_test", A4)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _h():
    h = host.FixtureHost.__new__(host.FixtureHost)
    h.target = T
    return h


A3 = {"schema_version": "TARGETED_EVIDENCE_SET_V1", "business": "LF", "target_ref": T,
      "status": "SOURCE_READBACK_PROCESSED_UNATTESTED", "source_refs": ["fixture://s/screen"],
      "target_resolution": {"source_ref": "fixture://s/screen"}}
A2 = {"schema_version": "ANALYSIS_CHANGE_CLASSIFICATION_V1", "target_ref": T,
      "change_type": "MODIFY"}
SEM = {"implementation_evidence": [
    {"path": "fe/page.tsx", "sha256": "a" * 64, "request": "req-1", "area": "FRONTEND"}]}


def test_modify_readback_maps_existing_screen_for_a4():
    rb = {"schema_version": "A4_EXISTING_IMPACT_CORE_READBACK_V1", "business": "LF",
          "target_ref": T, "source_attested": False}
    rb.update(_h().existing_readback(SEM, A3))
    out = _a4().run(A3, A2, rb)
    assert out["business"] == "LF" and out["technical_root_ref"] == "impl://" + T
    assert out["target_change_action"] == "MODIFY"
    assert [x["affected_ref"] for x in out["direct_impacts"]] == ["repo://fe/page.tsx@" + "a" * 64]
    codes = [x["code"] for x in out["unresolved_material_impacts"]]
    assert "A4_TARGET_NOT_MAPPED_TO_INVENTORY_OBJECT" not in codes
    assert out["dependency_paths"] == []


def test_modify_readback_without_evidence_blocks():
    with pytest.raises(Exception, match="SBX_A4_EXISTING_EVIDENCE_MISSING"):
        _h().existing_readback({}, A3)


def test_modify_readback_requires_screen_source_in_a3():
    with pytest.raises(Exception, match="SBX_A4_EXISTING_EVIDENCE_MISSING"):
        _h().existing_readback(SEM, dict(A3, source_refs=["other"]))
