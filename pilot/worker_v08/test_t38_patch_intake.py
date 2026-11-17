"""T38: unapplicable patches are rejected at intake; old runs can be forgiven."""
import json
import subprocess

import native_intake_defect as d
from native_proposal_push_guard import patch_applies

BASE = "b" * 40


def _git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def test_patch_applies_against_base_index(tmp_path):
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "a.txt").write_text("uno\ndos\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x")
    base = _git(tmp_path, "rev-parse", "HEAD")
    good = "--- a/a.txt\n+++ b/a.txt\n@@ -1,2 +1,2 @@\n uno\n-dos\n+tres\n"
    corrupt = "--- a/a.txt\n+++ b/a.txt\n@@ -1,2 +1,5 @@\n uno\n-dos\n+tres\n"
    assert patch_applies(tmp_path, base, good) is True
    assert patch_applies(tmp_path, base, corrupt) is False
    assert (tmp_path / "a.txt").read_text() == "uno\ndos\n"  # working tree untouched


def _write(root, **over):
    data = {"schema_version": d.SCHEMA, "task": "req9backend2", "code": d.CODE,
            "base_head_sha": BASE, "reason": "parche corrupto",
            "forgiven": [{"run_id": 5, "proposal_commit_sha": "c" * 40, "task_pack_sha256": "e" * 64}]}
    data.update(over)
    f = root / "pilot/worker_v08/intake_defects"
    f.mkdir(parents=True, exist_ok=True)
    (f / "req9backend2.json").write_text(json.dumps(data))


def test_record_forgives_only_for_registered_base(tmp_path):
    _write(tmp_path)
    rec = {"task_spec": {"base_head_sha": BASE}}
    assert set(d.verified_intake_defects(tmp_path, "req9backend2", rec)) == {5}
    assert d.verified_intake_defects(tmp_path, "req9backend2",
                                     {"task_spec": {"base_head_sha": "a" * 40}}) == {}


def test_bad_records_are_ignored(tmp_path):
    rec = {"task_spec": {"base_head_sha": BASE}}
    for over in ({"code": "OTHER"}, {"forgiven": []}, {"reason": ""}, {"extra": 1}):
        _write(tmp_path, **over)
        assert d.verified_intake_defects(tmp_path, "req9backend2", rec) == {}, over
