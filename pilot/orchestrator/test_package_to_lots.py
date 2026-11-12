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


def test_committed_owner_and_analysis_bound():
    root = bridge.ROOT
    run = root / "pilot/runs/f5-login"
    package = json.loads((run / "analysis.json").read_text())
    decision = bridge._decision(package, run, "f5-login")
    assert decision["decision_type"] == "OWNER_DECISION_SANDBOX"
    assert len(decision["requirement_ids"]) == 6
    assert len(decision["front_ids"]) == 19
    assert decision["analysis_gap_pending_before_lf"] is True
    assert decision["data_migration_required"] is False
    assert decision["default_users_source"] == "apps/time-service/.env.example"
    assert decision["password_hash_algorithm"] == "BCrypt"


def test_separate_unregistered_pg00_and_six_business_rules():
    root = bridge.ROOT
    folder = root / ".lf/worker-context/f5backend"
    tech = json.loads((folder / "reglas_tecnicas.json").read_text())
    business = json.loads((folder / "reglas_negocio.json").read_text())
    assert tech == bridge.technical_rules("BACKEND")
    assert set(tech["families"]) == {"STD-BE", "STD-SEC"}
    assert business["registration_status"] == "NOT_REGISTERED"
    assert business["production_authority"] is False
    assert len(business["rules"]) == len(business["requirements"]) == 6
    assert {r["requirement_id"] for r in business["rules"]} == {
        r["requirement_id"] for r in business["requirements"]}
    assert not (root/".lf/worker-context/f5data").exists()


def test_owner_decision_one_real_pg04_lot(tmp_path):
    import shutil
    folder = tmp_path / "pilot/runs/f5-login"
    folder.mkdir(parents=True)
    source = bridge.ROOT / "pilot/runs/f5-login"
    for name in ("request.md", "analysis.json", "owner_area_decision.json"):
        shutil.copyfile(source / name, folder / name)
    intake.accept(tmp_path, "f5-login")
    out = bridge.prepare(tmp_path, "f5-login", base_head_sha="d940576ffea313e2ee62060e3f289c6825f83776")
    assert out["schema_version"] == "CP33_LOTS_CANDIDATE_V1"
    assert out["pg01_status"] == "FIXTURE_UNATTESTED"
    assert out["worker_invoked"] is False
    assert len(out["lots"]) == 1
    lot = out["lots"][0]
    assert lot["area"] == "BACKEND"
    assert lot["profile_code"] == "PERFIL-PROG-BACKEND-SPRING-EXP"
    assert len(lot["write_paths"]) == 4 <= 6
    assert all(x.startswith("apps/time-service/src/main/java/lf/sandbox/time/auth/")
               and x.endswith(".java") for x in lot["write_paths"])
    assert lot["depends_on"] == []
    assert lot["requirement_ids"] == sorted(
        x["requirement_id"] for x in json.loads((folder/"analysis.json").read_text())["requirements"])
    rules = json.loads((tmp_path/".lf/worker-context/f5backend/reglas_negocio.json").read_text())
    assert len(rules["rules"]) == 6
    assert rules["registration_status"] == "NOT_REGISTERED"
    assert json.loads((folder/"state.json").read_text())["stage"] == "LOTS_PLANNED"
    assert (folder/"lots.json").read_bytes() == intake.canonical(out)
    assert bridge.prepare(tmp_path,"f5-login") == out


def test_owner_decision_absent_still_blocks(tmp_path):
    import shutil
    folder = tmp_path / "pilot/runs/f5-login"
    folder.mkdir(parents=True)
    source = bridge.ROOT / "pilot/runs/f5-login"
    for name in ("request.md", "analysis.json"):
        shutil.copyfile(source/name, folder/name)
    intake.accept(tmp_path,"f5-login")
    with pytest.raises(bridge.PackageLotsBlocked,
                       match="F51_DATA_REQUIREMENT_NOT_SOURCE_BOUND"):
        bridge.prepare(tmp_path,"f5-login", base_head_sha="d940576ffea313e2ee62060e3f289c6825f83776")
    assert not (folder/"lots.json").exists()


def test_owner_decision_corrupt_fails_closed(tmp_path):
    import shutil
    folder=tmp_path/"pilot/runs/f5-login"
    folder.mkdir(parents=True)
    source=bridge.ROOT/"pilot/runs/f5-login"
    for name in ("request.md","analysis.json","owner_area_decision.json"):
        shutil.copyfile(source/name,folder/name)
    intake.accept(tmp_path,"f5-login")
    decision=json.loads((folder/"owner_area_decision.json").read_text())
    decision["requirement_ids"].pop()
    (folder/"owner_area_decision.json").write_text(json.dumps(decision))
    with pytest.raises(bridge.PackageLotsBlocked,match="F51_OWNER_DECISION_INVALID"):
        bridge.prepare(tmp_path,"f5-login",base_head_sha="d940576ffea313e2ee62060e3f289c6825f83776")
