"""T4: genuine A9 screen chains and independent randomized scenario (offline Worker).

The fixtures and disposable selector are reused from T2, not copied or
rewritten. No ciphertext is opened, no examination is synthesized.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pilot.orchestrator import package_to_lots
from pilot.orchestrator.test_contract_t2 import scenario, DB_ONLY
from pilot.orchestrator.t4_admission import (
    missing_exam, public_exam_request, registration_variant, require_green_base,
)

@DB_ONLY
@pytest.mark.parametrize("kind", ["first", "second", "synthetic"])
def test_generated_chain_roots_request_public_exam_without_hand_registration(tmp_path, kind):
    request = "t4-" + kind
    folder, _ = scenario(tmp_path, kind, slug=request)
    lots = package_to_lots.prepare(tmp_path, request, base_head_sha="a" * 40)
    plan_path = tmp_path / "pilot/orchestrator/chain_plans" / (request + ".json")
    plan = json.loads(plan_path.read_text("utf-8"))
    by_id = {lot["id"]: lot for lot in lots["lots"]}
    roots = [lot for lot in lots["lots"] if not lot["depends_on"]]
    assert roots and len(plan["bindings"]) == len(lots["lots"])
    require_green_base("a" * 40, lambda _: {"total_count": 1, "workflow_runs": [{
        "head_sha": "a" * 40, "head_branch": "main", "event": "push",
        "status": "completed", "conclusion": "success", "run_attempt": 1,
        "created_at": "2026-11-13T00:00:00Z", "id": 1}]})
    for entry in plan["bindings"]:
        lot = by_id[entry["lot_id"]]
        task = entry["task_name"]
        assert missing_exam(tmp_path, task)
        title, body = public_exam_request(tmp_path, request, entry, lot)
        assert title == "EXAM_REQUEST: " + task
        for req in lot["requirement_ids"]:
            assert req in body
        for path in lot["write_paths"]:
            assert path in body
        assert "holdout_sha256" not in body
        assert "recipient" not in body
        # The title and requested ID are derived, never hardcoded from a case.
        (tmp_path / "pilot/worker_v08/native_tasks").mkdir(parents=True, exist_ok=True)
        assert registration_variant(tmp_path, task, entry["template_path"],
                                    "b" * 64) == task
    assert all(r["id"] in by_id for r in roots)
