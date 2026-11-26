"""Synthetic phase-1 controls; real Git, mocked Maven (no network)."""
from __future__ import annotations

import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "vendor/programming-agent/src"))

from programming_agent_runner.worker_spec import AcceptanceCommand, WorkerTaskSpec
import native_format_preflight as preflight


JAVA = "service/src/main/java/Example.java"
POM = "service/pom.xml"
ORIGINAL = "class Example {}\n"
CONFIG = {"components": {"api": {
    "kind": "maven", "root": "service", "build_file": POM,
    "source_roots": ["service/src/main/java"],
}}}
CHECK = AcceptanceCommand("format", ("mvn", "-B", "-q", "-f", POM, "spotless:check"), 5, 16000)


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


@pytest.fixture
def baseline(tmp_path):
    source = tmp_path / "baseline"
    source.mkdir()
    (source / JAVA).parent.mkdir(parents=True)
    (source / JAVA).write_text(ORIGINAL)
    (source / POM).write_text("<project/>")
    # A control-plane file must never be copied into the format workspace.
    (source / "control.txt").write_text("not format input")
    git(source, "init", "-q")
    git(source, "add", ".")
    git(source, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "base")
    spec = WorkerTaskSpec(
        schema_version=1, task_id="synthetic", objective="format test",
        base_head_sha=git(source, "rev-parse", "HEAD"), source_snapshot_sha256="a"*64,
        context_path_patterns=(POM,), write_path_patterns=(JAVA,),
        protected_path_patterns=(POM, "control.txt"), acceptance_commands=(CHECK,),
        max_attempts=1, max_patch_bytes=60000, max_changed_files=3,
        max_context_bytes=200000, allow_deletions=False,
    )
    return source, spec


def proposal(path=JAVA, old="class Example {}", new="class Example { int x; }"):
    return {"schema_version": 1, "summary": "synthetic change", "changed_paths": [path],
            "patch": f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n-{old}\n+{new}\n"}


def test_valid_format(baseline, monkeypatch):
    source, spec = baseline
    seen = []
    monkeypatch.setenv("GH_TOKEN", "not-for-format")
    def run(command, workspace, env):
        seen.append(workspace)
        assert command == CHECK
        assert (workspace / JAVA).read_text() == "class Example { int x; }\n"
        assert not (workspace / "control.txt").exists()
        assert "GH_TOKEN" not in env
        assert Path(env["HOME"]).is_dir()
        return 0, ""
    monkeypatch.setattr(preflight, "_run", run)
    assert preflight.prevalidate(source, spec, proposal(), CONFIG).status == "PASS"
    assert (source / JAVA).read_text() == ORIGINAL
    assert not seen[0].exists()
    assert git(source, "status", "--porcelain") == ""


def test_invalid_format_and_corrected_submission(baseline, monkeypatch):
    source, spec = baseline
    def run(command, workspace, env):
        if "int  x" in (workspace / JAVA).read_text():
            return 1, "[ERROR] The following files had format violations:\n[ERROR]     src/main/java/Example.java\n"
        return 0, ""
    monkeypatch.setattr(preflight, "_run", run)
    bad = proposal(new="class Example { int  x; }")
    result = preflight.prevalidate(source, spec, bad, CONFIG)
    assert (result.status, result.reason, result.paths) == (
        "FORMAT_FAIL", "SPOTLESS_VIOLATIONS", (JAVA,))
    assert "int  x" in bad["patch"]
    assert preflight.prevalidate(source, spec, proposal(), CONFIG).status == "PASS"
    assert (source / JAVA).read_text() == ORIGINAL


@pytest.mark.parametrize("failure,reason", [
    (FileNotFoundError("mvn"), "FORMAT_EXECUTION_FAILED"),
    (subprocess.TimeoutExpired("mvn", 5), "FORMAT_TIMEOUT"),
])
def test_infrastructure_exception(baseline, monkeypatch, failure, reason):
    source, spec = baseline
    def run(*args):
        raise failure
    monkeypatch.setattr(preflight, "_run", run)
    result = preflight.prevalidate(source, spec, proposal(), CONFIG)
    assert (result.status, result.reason) == ("INFRA_ERROR", reason)


def test_generic_maven_failure_is_not_format(baseline, monkeypatch):
    source, spec = baseline
    monkeypatch.setattr(preflight, "_run", lambda *a: (1, "[ERROR] Could not resolve plugin"))
    assert preflight.prevalidate(source, spec, proposal(), CONFIG).status == "INFRA_ERROR"


@pytest.mark.parametrize("path", ["outside.java", POM])
def test_outside_scope_or_protected(baseline, monkeypatch, path):
    source, spec = baseline
    monkeypatch.setattr(preflight, "_run", lambda *a: pytest.fail("must not execute"))
    assert preflight.prevalidate(source, spec, proposal(path), CONFIG).status == "INVALID_PROPOSAL"


def test_no_spotless(baseline, monkeypatch):
    source, spec = baseline
    spec = replace(spec, acceptance_commands=(AcceptanceCommand("package", ("mvn", "package"), 5, 1024),))
    monkeypatch.setattr(preflight, "_run", lambda *a: pytest.fail("must not execute"))
    assert preflight.prevalidate(source, spec, proposal(), CONFIG).status == "SKIPPED"


def test_unsupported_command_fails_closed(baseline, monkeypatch):
    source, spec = baseline
    spec = replace(spec, acceptance_commands=(replace(CHECK, argv=CHECK.argv + ("-Dskip=true",)),))
    monkeypatch.setattr(preflight, "_run", lambda *a: pytest.fail("must not execute"))
    assert preflight.prevalidate(source, spec, proposal(), CONFIG).status == "INFRA_ERROR"


def test_unapplicable_patch(baseline, monkeypatch):
    source, spec = baseline
    monkeypatch.setattr(preflight, "_run", lambda *a: pytest.fail("must not execute"))
    assert preflight.prevalidate(source, spec, proposal(old="different baseline"), CONFIG).status == "INVALID_PROPOSAL"
