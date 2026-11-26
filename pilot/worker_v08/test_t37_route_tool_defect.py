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


def test_preacceptance_exact_control_bytes_and_unchanged_registration(tmp_path):
    import hashlib

    tool = tmp_path / t.PREACCEPTANCE_TOOL
    tool.parent.mkdir(parents=True)
    tool.write_bytes(b"fixed guard")
    data = {"schema_version": t.PREACCEPTANCE_SCHEMA, "task": "req9contrato1",
            "tool": t.PREACCEPTANCE_TOOL, "blocked_code": "DUPLICA_COMPONENTE_EXISTENTE",
            "base_head_sha": OLD, "superseded_control_sha": "c" * 40,
            "current_control_sha": NEW, "superseded_tool_sha256": "1" * 64,
            "current_tool_sha256": hashlib.sha256(tool.read_bytes()).hexdigest(),
            "forgiven": [{"run_id": 7, "proposal_commit_sha": "e" * 40,
                          "task_pack_sha256": "d" * 64}],
            "reason": "signature false positive reproduced"}
    folder = tmp_path / "pilot/worker_v08/route_tool_defects"
    folder.mkdir(parents=True)
    file = folder / "req9contrato1.json"
    reg = {"task_spec": {"base_head_sha": OLD}}
    file.write_text(json.dumps(data))
    assert t.verified_route_tool_defects(tmp_path, "req9contrato1", reg) == {
        7: {"proposal_commit_sha": "e" * 40, "task_pack_sha256": "d" * 64}}
    assert not t.verified_route_tool_defects(tmp_path, "req9contrato1", REC)
    for over in ({"tool": "apps/time-service/build.sh"},
                 {"blocked_code": "REUTILIZACION_INDETERMINADA"},
                 {"superseded_control_sha": NEW},
                 {"superseded_tool_sha256": data["current_tool_sha256"]},
                 {"forgiven": [data["forgiven"][0]] * 2},
                 {"current_tool_sha256": "2" * 64}):
        file.write_text(json.dumps({**data, **over}))
        assert not t.verified_route_tool_defects(tmp_path, "req9contrato1", reg), over
    file.write_text(json.dumps(data))
    tool.write_bytes(b"drifted guard")
    assert not t.verified_route_tool_defects(tmp_path, "req9contrato1", reg)


def test_preacceptance_feedback_is_narrow():
    import pytest
    from pilot.orchestrator.route_tool_defect import preacceptance_failure

    row = {"name": "reuse-component-guard", "status": "FAIL", "returncode": 1,
           "reason": "DUPLICA_COMPONENTE_EXISTENTE:signature:src/Controller.java",
           "stdout_excerpt": "", "stderr_excerpt": ""}
    feedback = {"schema_version": "LF_NATIVE_VISIBLE_FEEDBACK_V1",
                "kind": "VISIBLE_ACCEPTANCE_ONLY", "attempt": 3,
                "commands": [row]}
    assert preacceptance_failure(feedback) == row["reason"]
    for over in ({"reason": "DUPLICA_COMPONENTE_EXISTENTE:type:type:LoginResult:src/A.java"},
                 {"reason": "REUTILIZACION_INDETERMINADA"},
                 {"name": "backend-package"}, {"returncode": 0},
                 {"status": "PASS"}, {"stderr_excerpt": "other failure"}):
        with pytest.raises(ValueError):
            preacceptance_failure({**feedback, "commands": [{**row, **over}]})
    with pytest.raises(ValueError):
        preacceptance_failure({**feedback, "commands": [row, row]})
