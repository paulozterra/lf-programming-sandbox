"""T17: real standards renderer and validator on five disposable generated branches."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import uuid

import pytest

from pilot.orchestrator.generated_branch_standards import synchronize

ROOT = Path(__file__).resolve().parents[2]
KINDS = {
    "registration": "lf/native-registration/t17fixture-",
    "integration": "lf/native-integration/t17fixture-run-",
    "registry": "lf/implemented-registry/",
    "generated-t7": "lf/generated-t7/",
    "request": "lf/request/req-",
}


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args],
                          capture_output=True, text=True, check=True).stdout.strip()


def check(root, *args):
    return subprocess.run([sys.executable, "standards/tools/changes.py", *args],
                          cwd=root, capture_output=True, text=True)


def change_fixture(paths):
    return {
        "schema_version": "LF_STANDARD_CHANGE_V1",
        "change_id": "CHG-9998",
        "title": "T17 prueba sintetica de rama generada",
        "change_class": "EDITORIAL",
        "trigger": {"kind": "OWNER", "reference": "T17 prueba offline"},
        "reason": "Verificar correspondencia exacta entre diff y campos derivados",
        "artifacts": [],
        "affected": {"rule_ids": [], "term_ids": [], "paths": paths},
        "existing_code_impact": {
            "mode": "NEW_OR_MODIFIED_ONLY", "baseline_ref": "standards/baseline/",
            "expected_direction": "NON_INCREASING"},
        "security_pin_invalidation": {"invalidates": False, "affected_artifacts": []},
        "requested_by": "owner", "approved_by": "paulozterra",
        "evidence": {"pr_url": ""},
    }


@pytest.mark.parametrize("kind", sorted(KINDS))
def test_generated_branch_matches_real_diff_and_official_checks(tmp_path, kind):
    checkout = tmp_path / "checkout"
    git(ROOT, "worktree", "add", "--detach", str(checkout), "origin/main")
    try:
        git(checkout, "config", "user.email", "t17@example.invalid")
        git(checkout, "config", "user.name", "T17 CI")
        identifier = uuid.uuid4().hex[:12]
        branch = KINDS[kind] + identifier
        git(checkout, "switch", "-c", branch)
        paths = [f"pilot/runs/t17fixture-{kind}/fixture.json"]
        if kind == "registration":
            paths.extend(f".lf/worker-context/t17fixture/{name}" for name in
                ("profile.md", "skills.md", "receipt.json", "lf_rules.md",
                 "lf_rules.receipt.json", "protocolo.md", "reutilizar.md"))
        for path in paths:
            file = checkout / path
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text("synthetic offline\n", encoding="utf-8")
        git(checkout, "add", "--", *paths)
        chg_file = None
        if kind in ("registration", "integration"):
            chg_file = "standards/changes/CHG-9998.json"
            (checkout / chg_file).write_text(json.dumps(change_fixture(["stale/path"]),
                                                       indent=2) + "\n")
        result = synchronize(checkout, kind, chg_file=chg_file)
        git(checkout, "commit", "-m", "T17 generated offline branch")
        real = git(checkout, "diff", "--name-only", "origin/main", "HEAD").splitlines()
        assert result == sorted(real)
        assert check(checkout, "render", "--check").returncode == 0
        assert check(checkout, "validate").returncode == 0
        assert check(checkout, "check", "--base", "origin/main").returncode == 0
        if chg_file:
            doc = json.loads((checkout / chg_file).read_text())
            assert doc["affected"]["paths"] == sorted(real)
            for name in paths:
                assert name in doc["affected"]["paths"]
            assert "stale/path" not in doc["affected"]["paths"]
            # Updating the PR URL must regenerate CAMBIOS in that commit too.
            url = "https://github.com/paulozterra/lf-programming-sandbox/pull/9998"
            doc["evidence"]["pr_url"] = url
            (checkout / chg_file).write_text(json.dumps(doc, indent=2) + "\n")
            # CHG auto-detection must work without per-branch hardcoding.
            synchronize(checkout, kind)
            git(checkout, "commit", "-m", "T17 link generated PR")
            assert url in (checkout / "standards/CAMBIOS.md").read_text()
            assert check(checkout, "render", "--check").returncode == 0
            assert json.loads((checkout / chg_file).read_text())["affected"]["paths"] == sorted(real)
        # CHG-bearing branches must REPAIR a stale derived view with the
        # official renderer; CHG-free branches cannot justify rewriting it.
        (checkout / "standards/CAMBIOS.md").write_text("stale derived\n")
        execution = subprocess.run(
            [sys.executable, str(ROOT / "pilot/orchestrator/generated_branch_standards.py"),
             "--kind", kind, "--root", str(checkout)],
            capture_output=True, text=True)
        if chg_file:
            assert execution.returncode == 0, execution.stderr
            assert check(checkout, "render", "--check").returncode == 0
            assert "stale derived" not in (checkout / "standards/CAMBIOS.md").read_text()
        else:
            assert execution.returncode != 0
            assert "GENERATED_BRANCH_STANDARDS_INVALID:" + kind in execution.stderr
    finally:
        git(ROOT, "worktree", "remove", "--force", str(checkout))


def test_invalid_change_schema_stops_official_gate(tmp_path):
    root = tmp_path / "checkout"
    git(ROOT, "worktree", "add", "--detach", str(root), "origin/main")
    try:
        p = root / "standards/changes/CHG-9998.json"
        data = change_fixture([])
        data["schema_version"] = "INVALID"
        p.write_text(json.dumps(data) + "\n")
        with pytest.raises(Exception):
            synchronize(root, "registration", chg_file="standards/changes/CHG-9998.json")
    finally:
        git(ROOT, "worktree", "remove", "--force", str(root))
