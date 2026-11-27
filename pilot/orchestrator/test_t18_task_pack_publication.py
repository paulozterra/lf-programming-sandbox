"""T18 offline: packed-registration hash, historical repair, sweep, human audit."""
from __future__ import annotations

from pilot.orchestrator.lifecycle_test_support import fake_api

import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from pilot.orchestrator import chain_lots
from pilot.orchestrator import task_pack_publication as pack

REQ, TASK = "req-901", "t18synthetic"


@pytest.fixture(autouse=True)
def isolate_retries_in_historical_task_pack_tests():
    # T18 validates deterministic repair; T20 exercises the independent
    # GitHub CI retry boundary against authenticated synthetic PRs.
    with patch.object(chain_lots, "retry_failed_bot_prs", return_value=[]), \
         patch.object(chain_lots, "retry_native_infra", return_value=[]), \
         patch.object(chain_lots, "recover_native_feedback", return_value=[]), \
         patch.object(chain_lots, "recover_route_defects", return_value=[]), \
          patch.object(chain_lots, "replay_native_integration", return_value=[]):
        yield


def fixture(root: Path, *, base="a" * 40):
    pack_rel, meta_rel = pack.paths_for(REQ, TASK)
    raw = b'{"messages":[],"schema_version":"T18_SYNTHETIC"}\n'
    sha = hashlib.sha256(raw).hexdigest()
    spec = {"schema_version": 1, "base_head_sha": base,
            "write_path_patterns": ["contracts/t18synthetic.openapi.yaml"],
            "max_changed_files": 1, "max_patch_bytes": 60000,
            "protected_path_patterns": ["pilot/**"]}
    record = root / f"pilot/worker_v08/native_tasks/{TASK}.json"
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps({"task_spec": spec}), encoding="utf-8")
    meta = {"schema_version": "CP34_NATIVE_PROPOSAL_REQUEST_V1",
            "task_name": TASK, "lot_id": "SOL-1",
            "task_spec_path": record.relative_to(root).as_posix(),
            "task_pack_path": pack_rel, "task_pack_sha256": sha,
            "base_head_sha": base,
            "production_authority": False, "model_invoked": False,
            "merge_authorized": False}
    return raw, sha, meta


def publish_files(root, raw, meta):
    pack_rel, meta_rel = pack.paths_for(REQ, TASK)
    a, b = root / pack_rel, root / meta_rel
    a.parent.mkdir(parents=True, exist_ok=True)
    a.write_bytes(raw)
    b.write_text(json.dumps(meta), encoding="utf-8")


def test_synthetic_registration_pack_and_request_are_in_diff_hash_verified(tmp_path):
    raw, sha, meta = fixture(tmp_path)
    publish_files(tmp_path, raw, meta)
    paths = pack.verify_published_pair(tmp_path, REQ, TASK, sha)
    assert paths == list(pack.paths_for(REQ, TASK))
    # This is the exact set the CP3.6 Draft stages before standards rendering.
    assert all((tmp_path / name).is_file() for name in paths)
    with pytest.raises(pack.TaskPackBlocked, match="TASK_PACK_HASH_MISMATCH"):
        pack.verify_published_pair(tmp_path, REQ, TASK, "0" * 64)
    (tmp_path / paths[0]).write_bytes(b'{"tampered":true}')
    with pytest.raises(pack.TaskPackBlocked, match="TASK_PACK_HASH_MISMATCH"):
        pack.verify_published_pair(tmp_path, REQ, TASK, sha)


def test_historical_cp36_artifact_is_attested_to_registered_base(tmp_path):
    raw, sha, meta = fixture(tmp_path)
    commands = []

    def fake_run(*args):
        commands.append(args)
        if args[:2] == ("gh", "api"):
            if "/runs?per_page=100" in args[2]:
                return json.dumps({"workflow_runs": [
                    {"id": 43750320423, "status": "completed", "conclusion": "success",
                     "event": "workflow_dispatch", "head_branch": "main"}]})
            return json.dumps({"artifacts": [
                {"name": "cp36-proposal-request-packs", "expired": False}]})
        if args[:3] == ("gh", "run", "download"):
            folder = Path(args[args.index("--dir") + 1])
            (folder / (TASK + ".task-pack.json")).write_bytes(raw)
            (folder / (TASK + ".proposal-request.json")).write_text(json.dumps(meta))
            return ""
        raise AssertionError(args)

    result = pack.legacy_artifact_reference(
        tmp_path, REQ, TASK,
        tmp_path / f"pilot/worker_v08/native_tasks/{TASK}.json",
        fake_run, chain_lots.REPO)
    assert result["task_pack_sha256"] == sha
    assert result["origin_run_id"] == 43750320423
    assert any(command[:3] == ("gh", "run", "download")
               for command in commands)


def test_repair_reexports_original_worker_base_and_keeps_registered_record(tmp_path):
    # Real disposable Git history: base context -> immutable task registration.
    root = tmp_path / "repo"
    root.mkdir()
    def git(*args):
        return subprocess.run(["git", "-C", str(root), *args], check=True,
                              capture_output=True, text=True).stdout.strip()
    git("init", "-b", "main")
    git("config", "user.name", "T18")
    git("config", "user.email", "t18@example.invalid")
    for name in ("profile.md", "skills.md", "receipt.json"):
        p = root / ".lf/worker-context" / TASK / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("synthetic\n")
    git("add", ".")
    git("commit", "-m", "synthetic registered context")
    base = git("rev-parse", "HEAD")
    raw, sha, meta = fixture(root, base=base)
    git("add", ".")
    git("commit", "-m", "synthetic registered task")
    before = (root / f"pilot/worker_v08/native_tasks/{TASK}.json").read_bytes()
    def capture(repo, spec_path, output_path):
        assert Path(repo).resolve() != root.resolve()
        assert json.loads(Path(spec_path).read_text())["base_head_sha"] == base
        output_path.write_bytes(raw)
        return hashlib.sha256(raw).hexdigest()
    modules = {
        "export_task_pack": SimpleNamespace(export=capture),
        "register_task_context": SimpleNamespace(
            canonical=lambda data: (json.dumps(data, sort_keys=True, separators=(",", ":"))
                                    + "\n").encode()),
    }
    with patch.dict(sys.modules, modules):
        published = pack.regenerate_pack_from_registered_base(
            root, REQ, TASK, {"task_pack_sha256": sha, "proposal_request": meta})
    assert published == list(pack.paths_for(REQ, TASK))
    assert (root / f"pilot/worker_v08/native_tasks/{TASK}.json").read_bytes() == before
    assert pack.verify_published_pair(root, REQ, TASK, sha) == published
    # Repair makes both pack files ready for the single new draft; no re-register.
    assert all(not p.startswith("pilot/worker_v08/native_tasks/") for p in published)


def test_mismatched_reexport_blocks_before_any_new_pr_and_notifies_issue(tmp_path):
    fixture(tmp_path)
    with patch.object(chain_lots, "ROOT", tmp_path), \
         patch.object(chain_lots, "pending_draft", return_value=False), \
         patch.object(chain_lots, "run", return_value=""), \
         patch.object(chain_lots, "legacy_artifact_reference",
                      return_value={"task_pack_sha256": "a" * 64}), \
         patch.object(chain_lots, "worktree", side_effect=lambda sha, branch, fn: fn(tmp_path)), \
         patch.object(chain_lots, "regenerate_pack_from_registered_base",
                      side_effect=pack.TaskPackBlocked("TASK_PACK_HASH_MISMATCH")), \
         patch.object(chain_lots, "comment_task_pack_mismatch") as notice, \
         patch.object(chain_lots, "draft") as draft:
        with pytest.raises(Exception, match="TASK_PACK_HASH_MISMATCH"):
            chain_lots.publish_missing_registered_pack(REQ, TASK, "b" * 40)
    notice.assert_called_once_with(REQ, TASK)
    draft.assert_not_called()


def test_next_sweep_repairs_registered_task_without_reregistering(tmp_path):
    fixture(tmp_path)
    head = "b" * 40
    lots = {"lots": []}
    binding = {"SOL-1": {"task_name": TASK}}
    existing = list(pack.paths_for(REQ, TASK))
    drafts = []

    def fake_worktree(base, branch, create):
        assert base == head and branch.startswith("lf/native-registration/pack-")
        return create(tmp_path)

    def fake_draft(root, branch, request, paths, reason, title):
        assert paths == existing and request == REQ
        drafts.append(branch)
        return {"draft_pr": "https://example.invalid/draft"}

    with patch.object(chain_lots, "ROOT", tmp_path), \
         patch.object(chain_lots, "check_main", return_value=head), \
         patch.object(chain_lots, "main_ci_decision", return_value="GREEN"), \
         patch.object(chain_lots, "retire_conflicted_generated", return_value=[]), \
         patch.object(chain_lots, "plans", return_value=[
             (REQ, lots, {"stage": "BLOCKED"}, binding)]), \
         patch.object(chain_lots, "route_request_metadata", return_value=True), \
         patch.object(chain_lots, "pending_draft", return_value=False), \
         patch.object(chain_lots, "run", return_value=""), \
         patch.object(chain_lots, "legacy_artifact_reference",
                      return_value={"task_pack_sha256": "a" * 64}), \
         patch.object(chain_lots, "regenerate_pack_from_registered_base",
                      return_value=existing), \
         patch.object(chain_lots, "worktree", side_effect=fake_worktree), \
         patch.object(chain_lots, "draft", side_effect=fake_draft), \
         patch.object(chain_lots, "api", side_effect=fake_api({})), \
         patch.object(chain_lots, "sweep_request_enabled", return_value=False), \
         patch.multiple(chain_lots,
                        recover_pending_worker=lambda *a, **kw: [],
                        recover_unstarted_integration=lambda *a, **kw: [],
                        sync_implemented_registry=lambda *a, **kw: {"status": "REGISTRY_CURRENT"}):
        results = chain_lots.process(sweep=True, base_sha=head)
    assert len(drafts) == 1
    assert any(x.get("status") == "TASK_PACK_REPAIR_DRAFT" for x in results)
    assert not any(x.get("status") == "DRAFT_PREPARED" for x in results)
