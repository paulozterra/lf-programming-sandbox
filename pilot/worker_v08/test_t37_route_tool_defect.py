"""T37: governed forgiveness of attempts spent on a fixed route tool."""
import json

import native_route_tool_defect as t

OLD, NEW = "a" * 40, "b" * 40
REC = {"task_spec": {"base_head_sha": NEW}}


def _write(root, **over):
    data = {"schema_version": t.SCHEMA, "task": "req9contrato1",
            "tool": "pilot/orchestrator/contract_validate.py",
            "blocked_code": "CONTRACT_FIELD_COVERAGE_MISSING",
            "superseded_base_sha": OLD, "current_base_sha": NEW,
            "superseded_tool_sha256": "1" * 64, "current_tool_sha256": "2" * 64,
            "forgiven": [{"run_id": 7, "proposal_commit_sha": "c" * 40,
                          "task_pack_sha256": "d" * 64}],
            "reason": "validator fixed on main"}
    data.update(over)
    d = root / "pilot/worker_v08/route_tool_defects"
    d.mkdir(parents=True, exist_ok=True)
    (d / "req9contrato1.json").write_text(json.dumps(data), "utf-8")


def test_valid_record_forgives_exact_runs(tmp_path):
    _write(tmp_path)
    assert t.verified_route_tool_defects(tmp_path, "req9contrato1", REC) == {
        7: {"proposal_commit_sha": "c" * 40, "task_pack_sha256": "d" * 64}}


def test_registration_must_be_repinned_to_current_base(tmp_path):
    _write(tmp_path)
    assert t.verified_route_tool_defects(
        tmp_path, "req9contrato1", {"task_spec": {"base_head_sha": OLD}}) == {}


def test_untrusted_tool_unchanged_tool_or_bad_rows_are_ignored(tmp_path):
    for over in ({"tool": "apps/time-service/build.sh"},
                 {"current_tool_sha256": "1" * 64},
                 {"superseded_base_sha": NEW},
                 {"forgiven": []},
                 {"forgiven": [{"run_id": 7}]},
                 {"reason": " "},
                 {"extra": 1}):
        _write(tmp_path, **over)
        assert t.verified_route_tool_defects(tmp_path, "req9contrato1", REC) == {}, over


def test_history_and_chain_consume_the_record():
    from pathlib import Path
    here = Path(t.__file__).parent
    assert "verified_route_tool_defects" in (here / "native_run_history.py").read_text("utf-8")
    assert "verified_route_tool_defects" in (here.parent / "orchestrator/chain_lots.py").read_text("utf-8")
