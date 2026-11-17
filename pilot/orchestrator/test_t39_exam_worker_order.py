"""T39: publish_exam builds each case in the Worker's order, so an exam that
trusts mtimes of a tracked build output is caught before publishing."""
import os
import subprocess
import time

import publish_exam as pe


def test_tracked_build_output_is_newer_than_overlaid_source(tmp_path):
    wt = tmp_path / "wt"
    (wt / "svc/src").mkdir(parents=True)
    (wt / "svc/target").mkdir(parents=True)
    (wt / "svc/src/A.java").write_text("old")
    (wt / "svc/target/app.jar").write_text("stale")
    subprocess.run(["git", "init", "-q"], cwd=wt, check=True)
    subprocess.run(["git", "add", "."], cwd=wt, check=True)
    ref = tmp_path / "ref/svc/src"
    ref.mkdir(parents=True)
    (ref / "A.java").write_text("new")
    seen = {}

    def fake_run(raw, case, python):
        src, jar = case / "svc/src/A.java", case / "svc/target/app.jar"
        seen["src"] = src.read_text()
        seen["jar_not_older"] = os.stat(jar).st_mtime_ns >= os.stat(src).st_mtime_ns
        return True
    pe.run_oracle, orig = fake_run, pe.run_oracle
    try:
        pe.exercise(b"{}", wt, tmp_path / "ref", [], "python3")
    except pe.ExamBlocked:
        pass  # no mutants: not relevant here
    finally:
        pe.run_oracle = orig
    assert seen == {"src": "new", "jar_not_older": True}
