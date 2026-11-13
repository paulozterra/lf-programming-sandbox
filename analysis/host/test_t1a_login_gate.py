"""T1-A: real A9 Login passes T1 atomizer without hand-written decisions."""
import json
import os
from pathlib import Path

import pytest
from analysis.host.run_a1_a9_fixture import run_f4
from pilot.orchestrator.package_to_lots import prepare


@pytest.mark.skipif(
    os.getenv("SELECTOR_EXP_DISPOSABLE_DB") != "YES" or
    not os.getenv("SELECTOR_EXP_TEST_DSN"),
    reason="Requires CP3.3 disposable PostgreSQL selector",
)
def test_login_two_source_areas_without_owner_or_fixture(tmp_path: Path):
    result = run_f4(tmp_path, slug="t1a-login")
    folder = tmp_path / "pilot/runs/t1a-login"
    assert result["state"]["stage"] == "INTAKE_ACCEPTED"
    assert result["package"]["package_readiness_candidate"] == "READY_CANDIDATE"
    assert not (folder / "owner_area_decision.json").exists()
    assert not (folder / "planning_fixture.json").exists()
    lots = prepare(tmp_path, "t1a-login", base_head_sha="a" * 40)
    assert [lot["area"] for lot in lots["lots"]] == ["BACKEND", "FRONTEND"]
    assert lots["lots"][0]["depends_on"] == []
    assert lots["lots"][1]["depends_on"] == [lots["lots"][0]["id"]]
    assert "planning_fixture_sha256" not in lots
    assert "atomized_inputs_sha256" in lots
    assert len(json.loads((folder / "atomized_inputs.json").read_text())["atoms"]) == 2
    assert (folder / "lots.json").is_file()
    atomized = json.loads((folder / "atomized_inputs.json").read_text())
    be = next(a for a in atomized["atoms"] if a["area"] == "BACKEND")
    fe = next(a for a in atomized["atoms"] if a["area"] == "FRONTEND")
    assert all("/time/login/" in p for p in be["paths"])
    assert "frontend/src/app/login/page.tsx" in fe["paths"]
    assert "frontend/src/lib/login.ts" in fe["paths"]
    assert not (folder / "owner_area_decision.json").exists()
    if os.getenv("T1A_ARTIFACT_DIR"):
        import shutil
        shutil.copytree(folder, Path(os.environ["T1A_ARTIFACT_DIR"]) / "login")
