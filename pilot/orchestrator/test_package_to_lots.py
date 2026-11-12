"""F5.1: original A9 packet, no fake PG04 area attribution."""
from pathlib import Path
import json
import pytest

from analysis.host.run_a1_a9_fixture import run_f4
from pilot.orchestrator import intake
from pilot.orchestrator import package_to_lots as bridge


def test_real_a9_intake_and_known_unassigned_rules(tmp_path):
    run = run_f4(tmp_path, slug="f5-login")
    assert run["state"]["stage"] == "INTAKE_ACCEPTED"
    original, state = bridge.read_package(tmp_path, "f5-login")
    assert original == run["package"]
    assessment = bridge.derive(original)
    assert assessment["schema_version"] == "F51_PACKAGE_TO_LOTS_ASSESSMENT_V1"
    assert {r["rule_code"] for r in assessment["business_rules_by_area"]["BACKEND"]} == {
        "SBX-R-LOCK", "SBX-R-HASH", "SBX-R-LOG"}
    assert assessment["business_rules_by_area"]["DATA"] == []
    assert {r["requirement_id"] for r in assessment["unassigned_business_rules"]} == {
        "REQ-SBX-R-USER", "REQ-SBX-R-PASS", "REQ-SBX-R-ERR"}
    assert assessment["pg04_area_resolution_pending"] is True
    with pytest.raises(bridge.PackageLotsBlocked,
                       match="F51_DATA_REQUIREMENT_NOT_SOURCE_BOUND"):
        bridge.prepare(tmp_path, "f5-login")
    assert not (tmp_path/"pilot/runs/f5-login/lots.json").exists()
    assert json.loads((tmp_path/"pilot/runs/f5-login/state.json").read_text())["stage"] == "INTAKE_ACCEPTED"


def test_pg00_two_rule_families_separate_from_business():
    data = bridge.technical_rules("DATA")
    be = bridge.technical_rules("BACKEND")
    assert set(data["families"]) == {"STD-DB", "STD-SEC"}
    assert set(be["families"]) == {"STD-BE", "STD-SEC"}
    assert all(x["domain"] in {"STD-DB", "STD-SEC"} for x in data["rules"])
    assert all(x["domain"] in {"STD-BE", "STD-SEC"} for x in be["rules"])
    assert data["production_authority"] is False
    assert be["production_authority"] is False


def test_committed_assessment_matches_real_a9_projection():
    root = bridge.ROOT
    original, state = bridge.read_package(root, "f5-login")
    assert state["stage"] == "INTAKE_ACCEPTED"
    recorded = json.loads((root/"pilot/runs/f5-login/assignment_assessment.json").read_text())
    assert bridge.derive(original) == recorded
    assert not (root/"pilot/runs/f5-login/lots.json").exists()


def test_separate_unregistered_pg00_and_business_blocks():
    root = bridge.ROOT
    assessment = json.loads((root/"pilot/runs/f5-login/assignment_assessment.json").read_text())
    for area, task in (("DATA", "f5data"), ("BACKEND", "f5backend")):
        base = root/".lf/worker-context"/task
        tech = json.loads((base/"reglas_tecnicas.json").read_text())
        business = json.loads((base/"reglas_negocio.json").read_text())
        assert tech == bridge.technical_rules(area)
        assert tech["families"] == (["STD-DB", "STD-SEC"] if area=="DATA" else ["STD-BE", "STD-SEC"])
        assert business["registration_status"] == "NOT_REGISTERED"
        assert business["rules"] == assessment["business_rules_by_area"][area]
        assert business["production_authority"] is False
        assert {r["rule_code"] for r in business["rules"]}.isdisjoint(
            {x["id"] for x in tech["rules"]})
