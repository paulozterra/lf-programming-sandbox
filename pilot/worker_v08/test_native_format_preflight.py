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
        assert (workspace / JAVA).read_text() == (ORIGINAL if workspace.name == "baseline" else "class Example { int x; }\n")
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
            return 1, "[ERROR] The following files had format violations:\n[ERROR]     src/main/java/Example.java\n[ERROR]         @@ -1,2 +1,1 @@\n"
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


def test_baseline_violation_not_charged(baseline, monkeypatch):
    source, spec = baseline
    calls = []
    def run(command, workspace, env):
        calls.append(workspace.name)
        return 1, "[ERROR] The following files had format violations:\n[ERROR]     src/main/java/Example.java\n"
    monkeypatch.setattr(preflight, "_run", run)
    result = preflight.prevalidate(source, spec, proposal(), CONFIG)
    assert result.status == "BASELINE_FAIL"
    assert calls == ["baseline"]


def test_unattributed_violation_never_format_fail(baseline, monkeypatch):
    source, spec = baseline
    monkeypatch.setattr(preflight, "_run", lambda c, w, e: (0, "") if w.name == "baseline" else (
        1, "[ERROR] The following files had format violations:\n[ERROR]     src/main/java/Other.java\n"))
    assert preflight.prevalidate(source, spec, proposal(), CONFIG).status == "INFRA_ERROR"


def test_req652_two_hunks_and_no_source_disclosure():
    # Actual diagnostic shape and coordinates from issue 652 feedback;
    # source lines intentionally replaced with synthetic sensitive content.
    relative = "src/main/java/lf/sandbox/time/sbxb2blogin/SbxB2bLoginService.java"
    path = "service/" + relative
    output = (
        "[ERROR] Failed to execute goal com.diffplug.spotless:spotless-maven-plugin:3.10.4:check "
        "(default-cli) on project time-service: The following files had format violations:\n"
        f"[ERROR]     {relative}\n"
        "[ERROR]         @@ -78,8 +78,7 @@\n"
        "[ERROR]         -password=synthetic_sensitive_value\n"
        "[ERROR]         @@ -161,8 +160,8 @@\n"
        "[ERROR]         +synthetic_source_content\n"
        "[ERROR]     src/main/java/Other.java\n"
        "[ERROR]         @@ -3 +3 @@\n"
    )
    paths, diagnostics = preflight._diagnose(output, (path,), "service")
    assert paths == (path,)
    assert len(diagnostics) == 2
    assert "original line 78, 8 lines; formatted line 78, 7 lines" in diagnostics[0]
    assert "original line 161, 8 lines; formatted line 160, 8 lines" in diagnostics[1]
    assert "synthetic" not in str(diagnostics)
    assert "Other.java" not in str(diagnostics)


def test_mixed_inert_files(baseline, monkeypatch):
    source, spec = baseline
    path = "docs/readme.md"
    (source / path).parent.mkdir()
    (source / path).write_text("old\n")
    git(source, "add", ".")
    git(source, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "docs")
    spec = replace(spec, base_head_sha=git(source, "rev-parse", "HEAD"), write_path_patterns=(JAVA, path))
    value = proposal()
    value["changed_paths"] = sorted([JAVA, path])
    value["patch"] += proposal(path, "old", "new")["patch"]
    def run(c, w, e):
        assert (w / path).read_text() == ("old\n" if w.name == "baseline" else "new\n")
        return 0, ""
    monkeypatch.setattr(preflight, "_run", run)
    assert preflight.prevalidate(source, spec, value, CONFIG).status == "PASS"


def test_authorized_build_change_deferred(baseline, monkeypatch):
    source, spec = baseline
    spec = replace(spec, protected_path_patterns=("control.txt",), write_path_patterns=(POM,))
    monkeypatch.setattr(preflight, "_run", lambda *a: pytest.fail("must not execute changed POM"))
    result = preflight.prevalidate(source, spec, proposal(POM, "<project/>", "<project />"), CONFIG)
    assert (result.status, result.reason) == ("SKIPPED", "FORMAT_UNSAFE_TO_PREFLIGHT")


def test_capture_overflow(tmp_path):
    command = AcceptanceCommand("synthetic", (sys.executable, "-c", "print('x'*1000000)"), 5, 1024)
    with pytest.raises(ValueError, match="output limit"):
        preflight._run(command, tmp_path, preflight._env(tmp_path))


def test_real_timeout(tmp_path):
    command = AcceptanceCommand("synthetic", (sys.executable, "-c", "import time; time.sleep(30)"), 1, 1024)
    with pytest.raises(subprocess.TimeoutExpired):
        preflight._run(command, tmp_path, preflight._env(tmp_path))


def test_git_environment_isolated(baseline, monkeypatch, tmp_path):
    source, spec = baseline
    poison = tmp_path / "poison"
    poison.write_text("[core]\n\thooksPath = /nonexistent\n")
    for key in ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_INDEX_FILE", "GIT_DIR",
                "GIT_WORK_TREE", "GIT_CONFIG_COUNT", "XDG_CONFIG_HOME"):
        monkeypatch.setenv(key, str(poison))
    real = subprocess.run
    def run(*args, **kwargs):
        env = kwargs["env"]
        assert "GIT_INDEX_FILE" not in env
        assert "GIT_DIR" not in env
        assert "GIT_WORK_TREE" not in env
        assert "GIT_CONFIG_COUNT" not in env
        assert env["GIT_CONFIG_GLOBAL"] == preflight.os.devnull
        assert env["XDG_CONFIG_HOME"] != str(poison)
        return real(*args, **kwargs)
    monkeypatch.setattr(preflight.subprocess, "run", run)
    monkeypatch.setattr(preflight, "_run", lambda *a: (0, ""))
    assert preflight.prevalidate(source, spec, proposal(), CONFIG).status == "PASS"
