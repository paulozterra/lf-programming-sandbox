"""T33.2: the T12 re-run of T7 (workflow_dispatch, rerun=true) parses the slug."""
from pathlib import Path
import re
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[2]
WF = ROOT / ".github/workflows/t7-request.yml"


def _rerun_block() -> str:
    doc = yaml.safe_load(WF.read_text("utf-8"))
    steps = doc["jobs"]["admit"]["steps"]
    run = next(s["run"] for s in steps
               if s.get("name") == "Stage generated evidence only in a governed Draft PR")
    block = run.split("then\n", 1)[1].split("\nfi\n", 1)[0]
    return block


def _run(block: str, tmp: Path, content: str) -> subprocess.CompletedProcess:
    (tmp / "t7-requests.txt").write_text(content, "utf-8")
    script = ("set -euo pipefail\nshort_sha=abcdef123456\n" + block
              + '\necho "BRANCH=$branch"\n')
    return subprocess.run(["bash", "-c", script], env={"RUNNER_TEMP": str(tmp), "PATH": "/usr/bin:/bin"},
                          capture_output=True, text=True)


def test_rerun_slug_is_parsed(tmp_path):
    out = _run(_rerun_block(), tmp_path, "pilot/runs/req-275/request.md\n")
    assert out.returncode == 0, out.stderr
    assert "BRANCH=lf/generated-t7/abcdef123456-req-275" in out.stdout


def test_rerun_rejects_bad_or_multiple_requests(tmp_path):
    block = _rerun_block()
    assert _run(block, tmp_path, "pilot/runs/x/request.md\n").returncode != 0
    assert _run(block, tmp_path, "pilot/runs/req-1/request.md\npilot/runs/req-2/request.md\n").returncode != 0


def test_escaped_sed_is_gone():
    assert not re.search(r"sed -n '1s\|", WF.read_text("utf-8"))
