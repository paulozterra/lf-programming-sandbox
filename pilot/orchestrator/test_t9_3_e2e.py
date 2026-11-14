"""T9.3: synthetic approved handoff -> trusted T7 -> real PG selector LOTS_PLANNED."""
import json
import os
import subprocess
from pathlib import Path

import pytest

from pilot.orchestrator.test_t72_dependencies import _scenario
from pilot.orchestrator import t7_entry
from pilot import train_handoff

@pytest.mark.skipif(
    os.environ.get("SELECTOR_EXP_DISPOSABLE_DB") != "YES"
    or os.environ.get("ATOMIZE_T1_SELECTOR") != "YES"
    or not os.environ.get("SELECTOR_EXP_TEST_DSN"),
    reason="Requires shared disposable selector setup")
def test_synthetic_trusted_handoff_to_t7_lots_planned(tmp_path):
    # A separate synthetic 13-file screen and local Git repository:
    # never reads, changes or replays the actual request #167.
    package, _, _, _, _ = _scenario(
        tmp_path, adds_rule=True, attested=True, backend_only=True)
    assert package["package_readiness_candidate"] == "READY_CANDIDATE"
    slug = "t72-after"
    folder = tmp_path / "pilot/runs" / slug
    assert (folder / "request.md").exists()

    # Route decision uses the same versioned map that Train uses.
    mapping = json.loads(train_handoff.MAP.read_text(encoding="utf-8"))
    assert train_handoff.route("lf/request/req-987654", mapping)[0]["workflow"] == "t7-request.yml"

    base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp_path,
                                   text=True).strip()
    output = t7_entry.process(tmp_path, slug, base)
    assert output["status"] == "LOTS_PLANNED", output
    state = json.loads((folder / "state.json").read_text(encoding="utf-8"))
    lots = json.loads((folder / "lots.json").read_text(encoding="utf-8"))
    assert state["stage"] == "LOTS_PLANNED"
    assert len(lots["lots"]) >= 1 and output["lots"] == len(lots["lots"])
    assert all(lot["write_paths"] for lot in lots["lots"])
    assert (folder / "chain_plan.json").is_file() or (
        tmp_path / "pilot/orchestrator/chain_plans" / (slug + ".json")).is_file()
