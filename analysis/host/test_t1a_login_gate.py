"""T1-A Login end-to-end negative gate, without owner decision or planning fixture."""
from pathlib import Path
import pytest
from analysis.host.run_a1_a9_fixture import run_f4
from pilot.orchestrator.package_to_lots import PackageLotsBlocked, prepare


def test_login_without_manual_decision_cannot_plan_unsupported_fronts(tmp_path: Path):
    result = run_f4(tmp_path, slug="t1a-login")
    run = tmp_path / "pilot/runs/t1a-login"
    assert result["state"]["stage"] == "INTAKE_ACCEPTED"
    assert result["package"]["package_readiness_candidate"] == "NEED_MORE_EVIDENCE"
    assert not (run / "owner_area_decision.json").exists()
    assert not (run / "planning_fixture.json").exists()
    with pytest.raises(PackageLotsBlocked, match="ATOM_AREA_UNRESOLVED"):
        prepare(tmp_path, "t1a-login", base_head_sha="a" * 40)
    assert not (run / "lots.json").exists()
