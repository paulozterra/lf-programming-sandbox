"""CHG-0247: R1 event trigger, anti-overflow and untrusted-run isolation."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
R1 = ROOT / ".github/workflows/r1-reconcile.yml"
CHAIN = ROOT / ".github/workflows/chain-lots.yml"
EXPECTED = {
    "sandbox-train",
    "LF Worker native (trusted workflow_run or manual, no API)",
    "CP3.5 native verified patch to draft PR",
    "T7 main request auto-admission (trusted, no model)",
    "T9 issue request intake",
    "CP3.6 chain after Train merge or spent native failure",
}


def workflow(path):
    # BaseLoader leaves the literal "on" key intact (YAML 1.1 SafeLoader
    # otherwise turns it into boolean True).
    return yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def test_six_completed_workflow_events_are_primary_and_cron_is_retained():
    r1 = workflow(R1)
    events = r1["on"]["workflow_run"]
    assert set(events["workflows"]) == EXPECTED
    assert events["types"] == ["completed"]
    assert r1["on"]["workflow_dispatch"] == ""
    assert r1["on"]["schedule"]
    assert r1["concurrency"]["group"] == "r1-state-reconcile-trigger"
    assert r1["concurrency"]["cancel-in-progress"] == "false"
    assert "github.ref == 'refs/heads/main'" in r1["jobs"]["wake"]["if"]
    assert ("github.event.workflow_run.head_repository.full_name == github.repository"
            in r1["jobs"]["wake"]["if"])


def test_no_checkout_no_event_code_and_sweep_run_name_is_marked():
    r1 = workflow(R1)
    job = r1["jobs"]["wake"]
    assert len(job["steps"]) == 1
    step = job["steps"][0]
    assert "uses" not in step
    script = step["run"]
    assert "actions/checkout" not in script
    assert "git checkout" not in script
    assert "github.event.workflow_run.head_sha" not in script
    assert "github.event.workflow_run.head_branch" not in script
    assert 'git/ref/heads/main' in script
    assert "R1_SWEEP_RECENT" in script
    assert "status=queued" in script and "status=in_progress" in script
    assert "status=completed&event=workflow_dispatch" in script
    assert "sweep=true" in script
    chain = workflow(CHAIN)
    assert "inputs.sweep" in chain["run-name"]
    assert "sweep {0}" in chain["run-name"]


def iso(dt):
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def completed(*, age_seconds, title="CP3.6 sweep 123456"):
    when = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    return {"id": 123456, "event": "workflow_dispatch",
            "status": "completed", "display_title": title,
            "updated_at": iso(when), "conclusion": "success"}


def execute_gate(tmp_path, *, queued=0, active=0, rows=(), malformed=False):
    r1 = workflow(R1)
    script = r1["jobs"]["wake"]["steps"][0]["run"]
    binary = tmp_path / "bin"
    binary.mkdir()
    fake_gh = binary / "gh"
    fake_gh.write_text(
        "#!/usr/bin/env python3\n"
        "import json,os,sys\n"
        "args=sys.argv[1:]\n"
        "if args[0]=='api':\n"
        "  url=args[1]\n"
        "  if 'status=queued' in url: print(os.environ['TEST_QUEUED'])\n"
        "  elif 'status=in_progress' in url: print(os.environ['TEST_ACTIVE'])\n"
        "  elif 'status=completed' in url: print(os.environ['TEST_ROWS'])\n"
        "  elif '/git/ref/heads/main' in url: print('b'*40)\n"
        "  else: raise AssertionError(url)\n"
        "elif args[:2]==['workflow','run']:\n"
        "  with open(os.environ['TEST_DISPATCH'], 'a') as f:\n"
        "    f.write(' '.join(args)+'\\n')\n"
        "else: raise AssertionError(args)\n",
        encoding="utf-8")
    fake_gh.chmod(0o755)
    dispatch_file = tmp_path / "dispatch.log"
    env = dict(os.environ, PATH=str(binary) + os.pathsep + os.environ["PATH"],
               GITHUB_REPOSITORY="paulozterra/lf-programming-sandbox",
               RUNNER_TEMP=str(tmp_path),
               TEST_QUEUED=str(queued), TEST_ACTIVE=str(active),
               TEST_ROWS=('{"workflow_runs":"wrong-type"}' if malformed
                          else json.dumps({"workflow_runs": list(rows)})),
               TEST_DISPATCH=str(dispatch_file))
    result = subprocess.run(["bash", "-c", script], env=env,
                            text=True, capture_output=True, timeout=20)
    lines = dispatch_file.read_text().splitlines() if dispatch_file.exists() else []
    return result, lines


@pytest.mark.parametrize("queued,active", [(1, 0), (0, 1), (2, 1)])
def test_inflight_chain_is_not_displaced(tmp_path, queued, active):
    result, dispatches = execute_gate(tmp_path, queued=queued, active=active)
    assert result.returncode == 0, result.stderr
    assert "R1_SWEEP_RECENT" in result.stdout
    assert dispatches == []


@pytest.mark.parametrize("title", [
    "CP3.6 sweep 123456", "CP3.6 123456",
])
def test_recent_completed_sweep_is_not_displaced(tmp_path, title):
    result, dispatches = execute_gate(
        tmp_path, rows=[completed(age_seconds=60, title=title)])
    assert result.returncode == 0, result.stderr
    assert "R1_SWEEP_RECENT" in result.stdout
    assert dispatches == []


@pytest.mark.parametrize("rows", [
    [],
    [completed(age_seconds=360)],
    [completed(age_seconds=60, title="CP3.6 req286backend2 PR 42")],
])
def test_old_or_absent_sweep_dispatches_exact_current_main(tmp_path, rows):
    result, dispatches = execute_gate(tmp_path, rows=rows)
    assert result.returncode == 0, result.stderr
    assert len(dispatches) == 1
    assert "chain-lots.yml" in dispatches[0]
    assert "sweep=true" in dispatches[0]
    assert "base_sha=" + "b" * 40 in dispatches[0]


def test_unreadable_chain_history_fails_closed(tmp_path):
    result, dispatches = execute_gate(tmp_path, malformed=True)
    assert result.returncode != 0
    assert dispatches == []


# CP3.6 completion must wake a fresh state sweep when no other chain owns
# the serialized slot. The step is executed with a fake gh, as above.
def test_cp36_non_sweep_completion_dispatches_fresh_sweep(tmp_path):
    assert "CP3.6 chain after Train merge or spent native failure" in EXPECTED
    result, dispatches = execute_gate(
        tmp_path, rows=[completed(age_seconds=30,
                                  title="CP3.6 req286backend2 PR 42")])
    assert result.returncode == 0, result.stderr
    assert len(dispatches) == 1
    assert "sweep=true" in dispatches[0]
    assert "base_sha=" + "b" * 40 in dispatches[0]


def test_cp36_completed_sweep_does_not_loop(tmp_path):
    result, dispatches = execute_gate(
        tmp_path, rows=[completed(age_seconds=30,
                                  title="CP3.6 sweep 123456")])
    assert result.returncode == 0, result.stderr
    assert "R1_SWEEP_RECENT" in result.stdout
    assert dispatches == []


def test_cp36_completion_with_other_chain_queued_does_not_dispatch(tmp_path):
    result, dispatches = execute_gate(tmp_path, queued=1)
    assert result.returncode == 0, result.stderr
    assert "R1_SWEEP_RECENT" in result.stdout
    assert dispatches == []
