"""T5 actual A9 Login, Notes and independent random FRONTEND plan tests.

Reuses DB-backed T2 source and selector, without modifying prior suites.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest
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
