"""General rules shared by CREATE and MODIFY, on synthetic inputs."""
import hashlib
import pytest

from pilot.orchestrator import declared_dependencies as dd
from pilot.orchestrator import reuse_assessment as ra


def test_endpoint_provider_is_the_attested_backend_lot(tmp_path):
    src = tmp_path / "Ctrl.java"
    src.write_text("x")
    sha = hashlib.sha256(src.read_bytes()).hexdigest()
    index = {"entries": [{"kind": "endpoint", "key": "GET /api/x", "path": "Ctrl.java", "sha256": sha}]}
    dep = {"kind": "endpoint", "key": "GET /api/x", "adds_rule": False}
    rows = [{"area": a, "status": "ATTESTED", "endpoints": ["GET /api/x"],
             "files": [{"path": "Ctrl.java", "sha256": sha}]} for a in ("CONTRATO", "FRONTEND")]
    rows.append({"area": "BACKEND", "status": "NO_DERIVABLE", "endpoints": ["GET /api/x"], "files": []})
    primary, _ = dd.resolve(index, {"entries": rows}, tmp_path, dep)
    assert primary["path"] == "Ctrl.java"


def test_component_test_root_belongs_to_code_area_not_resource_area():
    mapping = ra._project_patterns() if False else None
    from pilot.config import project_config as pc
    comp = pc.area_component("BACKEND", "maven")
    test_root = comp["test_roots"][0].rstrip("/")
    source = comp["source_roots"][0].rstrip("/") + "/"
    resource = comp["resource_roots"][0].rstrip("/") + "/db/"
    area = ra._path_area(test_root + "/x/SomeTest.java",
                         {"BACKEND": source, "DATA": resource, "FRONTEND": "frontend-synth/"})
    assert area == "BACKEND"
    with pytest.raises(ra.ReuseBlocked):
        ra._path_area("nowhere/x.txt", {"BACKEND": source, "DATA": resource})


def test_existing_atoms_cite_as_is_and_sealed_delta():
    import sys
    sys.path.insert(0, "pilot/orchestrator")
    import plan_lots
    pkg = {"classification": {"implementation_state": "EXISTING"},
           "request_context": {"target_ref": "SBX-SYNTH"},
           "non_atomized_fronts": [{"obligation_mode": "MODIFY_SCOPE", "candidate_ref": "repo://f@1"}]}
    ev = plan_lots._state_evidence(pkg, {"reuse_assessment_sha256": "c" * 64}, {"atom_id": "ATOM-1"})
    assert ev == {"as_is_ref": "impl://SBX-SYNTH",
                  "delta_ref": "reuse-assessment://sha256:" + "c" * 64 + "#ATOM-1"}
    new = dict(pkg, classification={"implementation_state": "NEW"})
    assert "bounded_reuse_assessment_ref" in plan_lots._state_evidence(new, {}, {"atom_id": "A"})
    with pytest.raises(plan_lots.PlanningBlocked, match="LOTES_MODIFICACION_SIN_EVIDENCIA"):
        plan_lots._state_evidence(dict(pkg, non_atomized_fronts=[]),
                                  {"reuse_assessment_sha256": "c" * 64}, {"atom_id": "A"})
