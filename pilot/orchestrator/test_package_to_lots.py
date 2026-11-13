"""F5.1: original A9 packet, no fake PG04 area attribution."""
from pathlib import Path
import json
import pytest

from analysis.host.run_a1_a9_fixture import run_f4
from pilot.orchestrator import intake
from pilot.orchestrator import package_to_lots as bridge


def test_current_a9_be_fe_is_not_legacy_owner_packet(tmp_path):
    run = run_f4(tmp_path, slug="f5-login")
    assert run["state"]["stage"] == "INTAKE_ACCEPTED"
    package, state = bridge.read_package(tmp_path, "f5-login")
    assert package == run["package"]
    areas = {f["execution_area"] for f in package["material_fronts"]}
    assert areas == {"BACKEND", "FRONTEND"}
    assert len(package["scope_proposals"]) == 2
    # The original F5.1 adapter is intentionally single-scope; rejecting
    # current A9 preserves the historical decision and avoids false replay.
    with pytest.raises(bridge.PackageLotsBlocked, match="F51_SCOPE_COUNT_UNSUPPORTED"):
        bridge.derive(package)
    with pytest.raises(bridge.PackageLotsBlocked, match="F51_SCOPE_COUNT_UNSUPPORTED"):
        bridge.prepare(tmp_path, "f5-login", legacy=True)
    assert not (tmp_path / "pilot/runs/f5-login/lots.json").exists()
    assert json.loads((tmp_path / "pilot/runs/f5-login/state.json").read_text())[
        "stage"] == "INTAKE_ACCEPTED"


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
    out = bridge.prepare(tmp_path, "f5-login", base_head_sha="d940576ffea313e2ee62060e3f289c6825f83776", legacy=True)
    assert out["schema_version"] == "CP33_LOTS_CANDIDATE_V1"
    fixture = json.loads((folder/"planning_fixture.json").read_text())
    assert fixture["owner_area_decision"]["front_ids"] == sorted(
        f["front_id"] for f in json.loads((folder/"analysis.json").read_text())["material_fronts"])
    from pilot.orchestrator import plan_lots
    package = json.loads((folder/"analysis.json").read_text())
    snapshot, mapping, pg01 = plan_lots._source_inputs(
        package, fixture["atoms"], fixture, package["request_sha256"], {})
    assert len(snapshot["material_front_coverage"]["material_fronts"]) == 19
    assert len(snapshot["scope_front_matrix"]) == 19
    assert pg01["source"] == "PG01_C4"

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
    assert bridge.prepare(tmp_path,"f5-login",legacy=True) == out


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
        bridge.prepare(tmp_path,"f5-login", base_head_sha="d940576ffea313e2ee62060e3f289c6825f83776", legacy=True)
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
        bridge.prepare(tmp_path,"f5-login",base_head_sha="d940576ffea313e2ee62060e3f289c6825f83776",legacy=True)
