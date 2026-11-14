"""T9.3: synthetic approved handoff -> trusted T7 -> real PG selector LOTS_PLANNED."""
import json
import os
import subprocess
import sys
import re
from pathlib import Path

import pytest

from pilot.orchestrator.test_t72_dependencies import _scenario
from pilot.workflow_python_commands import commands
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
    # Same published registry contract as T7, empty for this isolated synthetic
    # repository. Never import any historical real request or user registry.
    registry = tmp_path / "pilot/registry/implemented.json"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(json.dumps({
        "schema_version": "T7_IMPLEMENTED_REGISTRY_V1", "entries": []
    }), encoding="utf-8")

    # Route decision uses the same versioned map that Train uses.
    mapping = json.loads(train_handoff.MAP.read_text(encoding="utf-8"))
    assert train_handoff.route("lf/request/req-987654", mapping)[0]["workflow"] == "t7-request.yml"

    base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp_path,
                                   text=True).strip()
    # Extract the executable form from the REAL T7 YAML, not a parallel
    # function call. Substituting only temporary fixture values preserves the
    # exact interpreter/module/argument contract.
    repo = Path(__file__).resolve().parents[2]
    workflow = repo / ".github/workflows/t7-request.yml"
    scripts = commands(workflow)
    assert ("module", "pilot.orchestrator.t7_entry") in scripts
    source = workflow.read_text(encoding="utf-8")
    assert re.search(
        r"python3 -m pilot[.]orchestrator[.]t7_entry --root [.] \\\\",
        source)
    argv = [sys.executable, "-m", "pilot.orchestrator.t7_entry",
            "--root", str(tmp_path), "--request-id", slug,
            "--base-head-sha", base]
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    completed = subprocess.run(argv, cwd=repo, env=env, text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               timeout=120)
    assert completed.returncode == 0, completed.stderr
    output = json.loads(completed.stdout.strip().splitlines()[-1])
    assert output["status"] == "LOTS_PLANNED", output
    state = json.loads((folder / "state.json").read_text(encoding="utf-8"))
    lots = json.loads((folder / "lots.json").read_text(encoding="utf-8"))
    assert state["stage"] == "LOTS_PLANNED"
    assert len(lots["lots"]) >= 1 and output["lots"] == len(lots["lots"])
    assert all(lot["write_paths"] for lot in lots["lots"])
    assert (folder / "chain_plan.json").is_file() or (
        tmp_path / "pilot/orchestrator/chain_plans" / (slug + ".json")).is_file()
