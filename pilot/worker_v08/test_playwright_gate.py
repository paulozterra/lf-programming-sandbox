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
    from pilot.orchestrator.generate_chain import acceptance
    commands = acceptance("FRONTEND", ["frontend/src/app/page.tsx"])
    browser = [entry for entry in commands if entry["name"] == "frontend-browser-visible"]
    assert len(browser) == 1
    assert browser[0]["argv"] == ["python3", "pilot/worker_v08/playwright_gate.py",
                                  "--path", "/", "--selector", "body"]
    assert browser[0]["timeout_seconds"] >= 200
    # Examiner can supply distinct flags inside the encrypted oracle's normal
    # AcceptanceCommand, but its content is never created or read here.
    from vendor.programming_agent.src.programming_agent_runner.worker_spec import _acceptance_commands
    examiner = _acceptance_commands([{
        "name": "browser-exam", "argv": ["python3",
        "pilot/worker_v08/playwright_gate.py", "--path", "/different",
        "--selector", "main", "--text", "visible result"],
        "timeout_seconds": 240, "max_output_bytes": 32000}])
    assert len(examiner) == 1


# The existing DB-backed A9 fixture is reused as-is; these are distinct
# scenarios, never special-cased inside browser_gate.
from pilot.orchestrator.test_contract_t2 import scenario, DB_ONLY
from pilot.orchestrator import package_to_lots


@DB_ONLY
@pytest.mark.parametrize("kind", ["first", "second", "synthetic"])
def test_login_notes_and_random_frontend_tasks_include_browser(tmp_path, kind):
    request = "t5-" + kind
    scenario(tmp_path, kind, slug=request)
    lots = package_to_lots.prepare(tmp_path, request, base_head_sha="a" * 40)
    frontend = [lot for lot in lots["lots"] if lot["area"] == "FRONTEND"]
    assert len(frontend) == 1
    plan = json.loads((tmp_path / "pilot/orchestrator/chain_plans"
                       / (request + ".json")).read_text())
    bindings = [b for b in plan["bindings"] if b["lot_id"] == frontend[0]["id"]]
    assert len(bindings) == 1
    template = json.loads((tmp_path / bindings[0]["template_path"]).read_text())
    commands = template["task_spec"]["acceptance_commands"]
    assert any(c["argv"][:2] == ["python3", "pilot/worker_v08/playwright_gate.py"]
               for c in commands)
    assert all(not c["name"].startswith("hidden") for c in commands)
