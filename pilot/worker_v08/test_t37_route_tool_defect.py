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


def _git(root, *args):
    import subprocess
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def _commit(root, message):
    _git(root, "add", ".")
    _git(root, "commit", "-qm", message)
    return _git(root, "rev-parse", "HEAD")


def _historical_fixture(root):
    import hashlib

    _git(root, "init", "-q")
    _git(root, "config", "user.name", "Test")
    _git(root, "config", "user.email", "test@example.invalid")
    tool = root / t.PREACCEPTANCE_TOOL
    tool.parent.mkdir(parents=True)
    tool.write_bytes(b"old guard")
    reg = {"task_spec": {"base_head_sha": OLD}}
    registration = root / "pilot/worker_v08/native_tasks/req9contrato1.json"
    registration.parent.mkdir()
    registration.write_text(json.dumps(reg))
    req_path = "pilot/runs/req-9/proposal_requests/req9contrato1.proposal-request.json"
    request = root / req_path
    request.parent.mkdir(parents=True)
    request.write_text(json.dumps({"task_name": "req9contrato1",
        "base_head_sha": OLD, "task_pack_sha256": "d" * 64}))
    old = _commit(root, "original")
    tool.write_bytes(b"fixed guard")
    new = _commit(root, "fix")
    data = {"schema_version": t.PREACCEPTANCE_SCHEMA, "task": "req9contrato1",
            "tool": t.PREACCEPTANCE_TOOL, "blocked_code": "DUPLICA_COMPONENTE_EXISTENTE",
            "base_head_sha": OLD, "superseded_control_sha": old,
            "current_control_sha": new,
            "superseded_tool_sha256": hashlib.sha256(b"old guard").hexdigest(),
            "current_tool_sha256": hashlib.sha256(b"fixed guard").hexdigest(),
            "registration_sha256": hashlib.sha256(registration.read_bytes()).hexdigest(),
            "request_path": req_path,
            "forgiven": [{"run_id": 7, "proposal_commit_sha": "e" * 40,
                          "task_pack_sha256": "d" * 64}],
            "reason": "signature false positive reproduced"}
    file = root / "pilot/worker_v08/route_tool_defects/req9contrato1/7.json"
    file.parent.mkdir(parents=True)
    file.write_text(json.dumps(data))
    _commit(root, "governed recovery")
    return reg, data, file, tool


def test_preacceptance_exact_control_bytes_and_unchanged_registration(tmp_path):
    reg, data, file, tool = _historical_fixture(tmp_path)
    expected = {7: {"proposal_commit_sha": "e" * 40, "task_pack_sha256": "d" * 64}}
    assert t.verified_route_tool_defects(tmp_path, "req9contrato1", reg) == expected
    assert not t.verified_route_tool_defects(tmp_path, "req9contrato1", REC)
    for over in ({"tool": "apps/time-service/build.sh"},
                 {"blocked_code": "REUTILIZACION_INDETERMINADA"},
                 {"superseded_control_sha": data["current_control_sha"]},
                 {"superseded_control_sha": "f" * 40},
                 {"current_control_sha": "f" * 40},
                 {"registration_sha256": "2" * 64},
                 {"superseded_tool_sha256": data["current_tool_sha256"]},
                 {"forgiven": [data["forgiven"][0]] * 2},
                 {"forgiven": [{**data["forgiven"][0], "task_pack_sha256": "9" * 64}]},
                 {"current_tool_sha256": "2" * 64}):
        file.write_text(json.dumps({**data, **over}))
        assert not t.verified_route_tool_defects(tmp_path, "req9contrato1", reg), over
    file.write_text(json.dumps(data))
    tool.write_bytes(b"future maintenance")
    _commit(tmp_path, "future tool version")
    assert t.verified_route_tool_defects(tmp_path, "req9contrato1", reg) == expected


def test_preacceptance_coexists_with_legacy(tmp_path):
    reg, data, file, tool = _historical_fixture(tmp_path)
    # The existing T37 schema remains independent of the new per-run record.
    _write(tmp_path, superseded_base_sha=NEW, current_base_sha=OLD,
           forgiven=[{"run_id": 6, "proposal_commit_sha": "c" * 40,
                      "task_pack_sha256": "d" * 64}])
    assert set(t.verified_route_tool_defects(tmp_path, "req9contrato1", reg)) == {6, 7}


def test_checkout_attestation_is_bounded_to_trusted_prefix():
    import pytest
    from pilot.orchestrator.route_tool_defect import checkout_sha_from_log

    prefix = ("2026-11-26T03:49:32.8210819Z [command]/usr/bin/git checkout --progress --force -B main refs/remotes/origin/main\n"
              "2026-11-26T03:49:32.9263013Z [command]/usr/bin/git log -1 --format=%H\n"
              "2026-11-26T03:49:32.9297894Z " + OLD + "\n")
    suffix = "git -C control fetch --no-tags origin $sha\n[command]/usr/bin/git log -1 --format=%H\n" + NEW
    assert checkout_sha_from_log(prefix + suffix) == OLD
    with pytest.raises(ValueError):
        checkout_sha_from_log(suffix)
    with pytest.raises(ValueError):
        checkout_sha_from_log(prefix + prefix + suffix)


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
