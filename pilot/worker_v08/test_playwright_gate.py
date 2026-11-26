"""T5 browser gate: no hidden oracle, keys, or external networking."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch
import pytest

from pilot.worker_v08 import playwright_gate as gate


def test_only_local_application_ports_allowed():
    for url in ("http://127.0.0.1:3000/", "http://localhost:8080/v3/api-docs",
                "ws://127.0.0.1:3000/_next/webpack-hmr", "http://[::1]:3000/"):
        assert gate.local_url(url)
    for url in ("https://example.org", "http://127.0.0.1:4444",
                "https://localhost:3000@evil.invalid/",
                "file:///etc/passwd", "http://10.0.0.1:3000/",
                "http://127.0.0.1.evil.invalid:3000/"):
        assert not gate.local_url(url)


def test_unsafe_browser_paths_block():
    for path in ("//example.org", "http://remote.test/", "/bad\\escape", "/line\nnext"):
        with pytest.raises(gate.BrowserBlocked, match="BROWSER_PATH_INVALID"):
            gate.check_path(path)


def test_missing_browser_is_explicit_no_approval(tmp_path):
    (tmp_path / "apps/time-service").mkdir(parents=True)
    (tmp_path / "apps/time-service/pom.xml").write_text("<project/>")
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend/package.json").write_text("{}")
    with patch.object(gate, "available", side_effect=gate.BrowserBlocked(
            "NAVEGADOR_NO_DISPONIBLE")), patch.object(gate, "_spawn") as launch:
        with pytest.raises(gate.BrowserBlocked, match="NAVEGADOR_NO_DISPONIBLE"):
            gate.verify(tmp_path, path="/", selector="main", text=None, title=None)
        launch.assert_not_called()


def test_application_start_failure_is_explicit(tmp_path):
    (tmp_path / "apps/time-service").mkdir(parents=True)
    (tmp_path / "apps/time-service/pom.xml").write_text("<project/>")
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend/package.json").write_text("{}")
    with patch.object(gate, "available"), patch.object(
            gate, "_spawn", side_effect=gate.BrowserBlocked("APP_NO_ARRANCA")):
        with pytest.raises(gate.BrowserBlocked, match="APP_NO_ARRANCA"):
            gate.verify(tmp_path, path="/", selector="main", text=None, title=None)


def test_no_app_files_is_failure_not_success(tmp_path):
    with pytest.raises(gate.BrowserBlocked, match="APP_NO_ARRANCA"):
        gate.verify(tmp_path, path="/", selector="main", text=None, title=None)


def test_frontend_generic_acceptance_and_exam_command_format():
    import sys
    orchestrator = str(Path(__file__).resolve().parents[1] / "orchestrator")
    if orchestrator not in sys.path:
        sys.path.insert(0, orchestrator)
    from pilot.orchestrator.generate_chain import acceptance
    commands = acceptance("FRONTEND", ["frontend/src/app/page.tsx"])
    browser = [entry for entry in commands if entry["name"] == "frontend-browser-visible"]
    assert len(browser) == 1
    assert browser[0]["argv"] == ["lf-python", "pilot/worker_v08/playwright_gate.py",
                                  "--path", "/", "--selector", "body"]
    assert browser[0]["timeout_seconds"] >= 200
    # Examiner can supply distinct flags inside the encrypted oracle's normal
    # AcceptanceCommand, but its content is never created or read here.
    import sys
    vendor = str(Path(__file__).resolve().parents[2] / "vendor/programming-agent/src")
    if vendor not in sys.path:
        sys.path.insert(0, vendor)
    from programming_agent_runner.worker_spec import _acceptance_commands
    examiner = _acceptance_commands([{
        "name": "browser-exam", "argv": ["python3",
        "pilot/worker_v08/playwright_gate.py", "--path", "/different",
        "--selector", "main", "--text", "visible result"],
        "timeout_seconds": 240, "max_output_bytes": 32000}])
    assert len(examiner) == 1




# --- Declarative visible suite (data-only cases) -------------------------
import json as _json

import pytest as _pytest

from pilot.worker_v08 import playwright_gate as _gate


def _write(tmp, name, data):
    folder = tmp / "suite"
    folder.mkdir(exist_ok=True)
    (folder / name).write_text(_json.dumps(data))
    return "suite"


def test_suite_accepts_declarative_cases(tmp_path):
    rel = _write(tmp_path, "a.json", {"covers": ["R1"], "cases": [
        {"id": "c1", "path": "/x", "selector": "main", "text": "Hola",
         "css": {"font-size": "16px"}, "box": {"width": 320, "tolerance_px": 2},
         "viewport": {"width": 1440, "height": 900}},
        {"id": "c2", "selector": ".err", "count": 0}]})
    assert [c["id"] for c in _gate.load_suite(tmp_path, rel)] == ["c1", "c2"]


def test_empty_or_missing_suite_has_no_cases(tmp_path):
    assert _gate.load_suite(tmp_path, "absent") == []


@_pytest.mark.parametrize("case", [
    {"id": "x", "selector": "main", "script": "alert(1)"},
    {"id": "x", "selector": "main", "path": "http://evil/"},
    {"id": "x", "selector": "main", "css": {"Font Size": "1"}},
    {"id": "x", "selector": "main", "box": {"width": -1}},
    {"id": "x", "selector": ""},
    {"id": "bad id!", "selector": "main"},
])
def test_case_with_code_or_unsafe_values_is_denied(tmp_path, case):
    rel = _write(tmp_path, "a.json", {"cases": [case]})
    with _pytest.raises(_gate.BrowserBlocked):
        _gate.load_suite(tmp_path, rel)


def test_duplicate_case_ids_and_parent_paths_are_denied(tmp_path):
    rel = _write(tmp_path, "a.json", {"cases": [{"id": "c", "selector": "a"}]})
    _write(tmp_path, "b.json", {"cases": [{"id": "c", "selector": "b"}]})
    with _pytest.raises(_gate.BrowserBlocked):
        _gate.load_suite(tmp_path, rel)
    with _pytest.raises(_gate.BrowserBlocked):
        _gate.load_suite(tmp_path, "../etc")


def test_repository_suite_is_valid():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    assert _gate.load_suite(root, "frontend/visible-tests")


def test_visibility_only_case_is_not_a_characterization(tmp_path):
    rel = _write(tmp_path, "a.json", {"cases": [{"id": "v", "selector": "main"}]})
    with _pytest.raises(_gate.BrowserBlocked, match="BROWSER_CASE_WITHOUT_ASSERTION"):
        _gate.load_suite(tmp_path, rel)


def test_every_css_and_box_assertion_gets_a_mutation():
    case = {"id": "c", "selector": "#x", "css": {"color": "rgb(0, 0, 0)", "font-size": "16px"},
            "box": {"width": 400, "height": 300, "tolerance_px": 2}}
    found = _gate.mutations(case)
    assert [sorted(m) for m in found] == [["color"], ["font-size"],
                                          ["max-width", "min-width", "width"],
                                          ["height", "max-height", "min-height"]]
    # the forced size is always outside the tolerance
    assert int(found[2]["width"][0][:-2]) - 400 > 2
    assert _gate.mutations({"id": "t", "selector": "a", "text": "x"}) == []


def test_app_start_flake_is_retried_once_but_assertions_never(monkeypatch):
    calls = []
    monkeypatch.setattr(_gate.time, "sleep", lambda s: None)
    def flaky(root, **kw):
        calls.append(1)
        if len(calls) == 1:
            raise _gate.BrowserBlocked("APP_NO_ARRANCA")
    monkeypatch.setattr(_gate, "_verify_once", flaky)
    _gate.verify(".", path="/", selector="main", text=None, title=None)
    assert len(calls) == 2
    calls.clear()
    monkeypatch.setattr(_gate, "_verify_once",
                        lambda root, **kw: (calls.append(1), (_ for _ in ()).throw(
                            _gate.BrowserBlocked("APP_NO_ARRANCA")))[1])
    with _pytest.raises(_gate.BrowserBlocked, match="APP_NO_ARRANCA"):
        _gate.verify(".", path="/", selector="main", text=None, title=None)
    assert len(calls) == _gate.APP_START_ATTEMPTS
    calls.clear()
    def wrong(root, **kw):
        calls.append(1)
        raise _gate.BrowserBlocked("BROWSER_ASSERTION_FAILED:c1")
    monkeypatch.setattr(_gate, "_verify_once", wrong)
    with _pytest.raises(_gate.BrowserBlocked, match="ASSERTION"):
        _gate.verify(".", path="/", selector="main", text=None, title=None)
    assert len(calls) == 1


def test_failed_start_says_component_cause_and_redacted_tail(tmp_path, capsys, monkeypatch):
    import sys as _sys
    from pilot.worker_v08 import playwright_gate as gate
    monkeypatch.setenv("DB_PASSWORD", "pw-not-echoed")
    script = ("import sys; print('Downloading spring-boot-maven-plugin'); "
              "print('url pw-not-echoed'); print('password=abcdefghijklmnopqrstu'); sys.exit(3)")
    proc = gate._spawn([_sys.executable, "-c", script], tmp_path)
    proc.wait(timeout=10)
    import pytest as _pytest
    with _pytest.raises(gate.BrowserBlocked, match="APP_NO_ARRANCA"):
        gate.wait_local(1, proc, seconds=2, name="BACKEND")
    err = capsys.readouterr().err
    assert "APP_NO_ARRANCA_DETALLE: BACKEND EXIT_3" in err
    assert "APP_NO_ARRANCA_INDICIO: BACKEND MAVEN_DEPENDENCY_TRANSFER" in err
    assert "Downloading spring-boot-maven-plugin" not in err
    gate._stop(proc)
    assert proc._lf_log.closed
    assert "pw-not-echoed" not in err and "abcdefghijklmnopqrstu" not in err


def test_diagnosis_never_echoes_arbitrary_child_output(tmp_path, capsys):
    import sys
    proc = gate._spawn([sys.executable, "-c", "print('unclassified-sensitive-value'); print('Address already in use')"], tmp_path)
    try:
        proc.wait(timeout=10)
        with pytest.raises(gate.BrowserBlocked, match="APP_NO_ARRANCA"):
            gate.wait_local(1, proc, seconds=2, name="FRONTEND")
        err = capsys.readouterr().err
        assert "FRONTEND EXIT_0" in err
        assert "FRONTEND PORT_IN_USE" in err
        assert "unclassified-sensitive-value" not in err
    finally:
        gate._stop(proc)


def test_diagnosis_bounded_tail_and_preserves_write_offset(tmp_path, capsys):
    import sys
    proc = gate._spawn([sys.executable, "-c", "print('Address already in use'); print('x' * 70000); print('Connection refused')"], tmp_path)
    try:
        proc.wait(timeout=10)
        pos = proc._lf_log.tell()
        gate._start_diagnosis("BACKEND", proc, 90)
        err = capsys.readouterr().err
        assert "DATABASE_CONNECTION" in err and "PORT_IN_USE" not in err
        assert proc._lf_log.tell() == pos
    finally:
        gate._stop(proc)
