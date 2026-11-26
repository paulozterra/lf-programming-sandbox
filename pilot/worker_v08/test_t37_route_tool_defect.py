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


def test_preacceptance_consumed_by_history_and_chain(tmp_path, monkeypatch):
    import native_run_history as history
    from pilot.orchestrator import chain_lots

    reg, data, file, tool = _historical_fixture(tmp_path)
    task = "req9contrato1"
    pack = "d" * 64
    def run(i, sha, status="completed"):
        return {"id": i, "status": status, "conclusion": "failure" if status == "completed" else None,
                "head_branch": "main", "run_attempt": 1, "event": "workflow_run",
                "display_title": f"lf-native-auto-lf/native-proposal/{task}-{sha}"}
    prior = [run(5, "a" * 40), run(6, "b" * 40), run(7, "e" * 40)]
    current = run(8, "f" * 40, "in_progress")
    proofs = {i: {"task_id": task, "attempt": i-4, "run_id": i,
                  "task_pack_sha256": pack} for i in (5, 6, 7)}
    monkeypatch.setattr(history, "__file__", str(tmp_path / "pilot/worker_v08/native_run_history.py"))
    monkeypatch.setattr(history, "storage_path", lambda kind, *p, root: root.joinpath("pilot/worker_v08/native_tasks", *p))
    monkeypatch.setattr(history, "_api", lambda *a: {"total_count": 4, "workflow_runs": prior + [current]})
    monkeypatch.setattr(history, "_artifact_json", lambda repo, token, rid: proofs[rid])
    out = tmp_path / "admit.json"
    assert history.admit_attempt(repository="paulozterra/lf-programming-sandbox", token="offline",
        task=task, attempt=None, run_id=8, run_attempt=1, sha="f" * 40, output=out,
        event="workflow_run", proposal_branch="lf/native-proposal/" + task) == 3
    assert json.loads(out.read_text())["route_defect_run_ids"] == [7]
    assert json.loads(out.read_text())["prior_run_ids"] == [5, 6]
    monkeypatch.setattr(chain_lots, "ROOT", tmp_path)
    monkeypatch.setattr(chain_lots, "storage_path", lambda kind, *p, root: root.joinpath("pilot/worker_v08/native_tasks", *p))
    monkeypatch.setattr(chain_lots, "api", lambda path: {"total_count": 3, "workflow_runs": prior})
    monkeypatch.setenv("GH_TOKEN", "offline")
    assert chain_lots.failed_lots({"lot": {"task_name": task}}) == {"lot": [5, 6]}


def test_producer_requires_exact_proof_and_three_replays(tmp_path, monkeypatch):
    import hashlib
    import subprocess
    import pytest
    from pilot.orchestrator import route_tool_defect as p
    import native_run_history as history
    from programming_agent_runner.hashutil import canonical_json_bytes

    reg, data, file, tool = _historical_fixture(tmp_path)
    task = data["task"]
    old, new = data["superseded_control_sha"], data["current_control_sha"]
    proposal = {"schema_version": 1, "summary": "synthetic", "patch": "synthetic patch",
                "changed_paths": ["src/A.java"]}
    envelope = {"author": "GPT_NATIVE", "proposal": proposal,
                "proposal_sha256": hashlib.sha256(canonical_json_bytes(proposal)).hexdigest(),
                "task_pack_sha256": "d" * 64}
    sha = "e" * 40
    proof = {"task_id": task, "attempt": 3, "run_id": 7, "task_pack_sha256": "d" * 64}
    reason = "DUPLICA_COMPONENTE_EXISTENTE:signature:src/A.java"
    feedback = {"schema_version": "LF_NATIVE_VISIBLE_FEEDBACK_V1",
                "kind": "VISIBLE_ACCEPTANCE_ONLY", "attempt": 3,
                "commands": [{"name": "reuse-component-guard", "status": "FAIL",
                    "returncode": 1, "reason": reason, "stdout_excerpt": "", "stderr_excerpt": ""}]}
    run = {"id": 7, "event": "workflow_run", "head_branch": "main", "status": "completed",
           "conclusion": "failure", "run_attempt": 1, "head_sha": old,
           "path": ".github/workflows/worker-native.yml", "repository": {"full_name": p.REPO},
           "display_title": f"lf-native-auto-lf/native-proposal/{task}-{sha}"}
    _git(tmp_path, "update-ref", "refs/remotes/origin/main", new)
    monkeypatch.setattr(p, "ROOT", tmp_path)
    monkeypatch.setattr(p, "storage_path", lambda kind, root: root / "pilot/runs")
    monkeypatch.setenv("GH_TOKEN", "offline")
    monkeypatch.setattr(p, "api", lambda path: run)
    monkeypatch.setattr(p, "feedback_for", lambda *args: feedback)
    monkeypatch.setattr(p, "attest_control_checkout", lambda rid, control: None)
    monkeypatch.setattr(history, "_artifact_json", lambda *args: proof)
    def sh(*args, **kwargs):
        if args[:2] == ("git", "fetch"):
            return ""
        if args[:2] == ("git", "show") and args[2].startswith(sha + ":"):
            return json.dumps(envelope)
        return subprocess.check_output(args, cwd=tmp_path, text=True)
    monkeypatch.setattr(p, "sh", sh)
    calls = []
    results = [reason, None, None]
    def replay(base, control, submitted, spec, **kw):
        assert base == OLD and submitted == proposal and spec == reg["task_spec"]
        calls.append((control, kw.get("replacement_guard")))
        return results[len(calls)-1]
    monkeypatch.setattr(p, "replay_preacceptance", replay)
    got = p.prove_preacceptance(task, [7], new, "synthetic")
    assert got["forgiven"] == data["forgiven"]
    assert calls == [(old, None), (old, b"fixed guard"), (new, None)]
    for values, code in [
        (["other", None, None], "SUPERSEDED_TOOL_DOES_NOT_REPRODUCE"),
        ([reason, reason, None], "ISOLATED_GUARD_STILL_FAILS"),
        ([reason, None, reason], "CURRENT_TOOL_STILL_FAILS")]:
        calls.clear()
        results[:] = values
        with pytest.raises(ValueError, match=code):
            p.prove_preacceptance(task, [7], new, "synthetic")
    calls.clear()
    proof["task_pack_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="ATTEMPT_PROOF_MISMATCH"):
        p.prove_preacceptance(task, [7], new, "synthetic")
    assert calls == []
    proof["task_pack_sha256"] = "d" * 64
    envelope["task_pack_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="PROPOSAL_PACK_MISMATCH"):
        p.prove_preacceptance(task, [7], new, "synthetic")
    assert calls == []
    with pytest.raises(ValueError, match="CONTROL_NOT_TRUSTED_MAIN"):
        p.prove_preacceptance(task, [7], "f" * 40, "synthetic")
