"""T19: offline end-to-end published request -> native envelope -> guard/client."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "vendor/programming-agent/src"))
sys.path.insert(0, str(ROOT / "pilot/worker_v08"))
sys.path.insert(0, str(ROOT / "pilot/orchestrator"))

from pilot.orchestrator.native_submission_contract import canonical, enrich_request
from pilot.orchestrator import chain_lots
from native_proposal_client import read_proposal_envelope, NativeProposalClient
from native_proposal_push_guard import validate_proposal_only, ProposalPushBlocked
import native_push_failure_notify as notifier
from programming_agent_runner.hashutil import canonical_json_bytes
from programming_agent_runner.worker_spec import parse_worker_task
from programming_agent_runner.worker_patch import parse_patch_proposal, inspect_patch

TASK = "fixture19"
REQUEST = "req-901"
BOT = "41898282+github-actions[bot]@users.noreply.github.com"
PATH = "contracts/fixture19.openapi.yaml"


def git(root, *args, env=None):
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True, text=True, env=env).stdout.strip()


def setup_repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "T19 Test")
    git(root, "config", "user.email", "test@example.invalid")
    request_folder = root / "pilot/runs" / REQUEST
    request_folder.mkdir(parents=True)
    (request_folder / "request_meta.json").write_text(json.dumps({"issue": 901, "author": "user"}))
    source = root / "pilot/worker_v08/native_tasks" / (TASK + ".json")
    source.parent.mkdir(parents=True)
    # Read-only synthetic derivation from the real Worker's accepted task schema.
    spec = json.loads((ROOT / "pilot/worker_v08/native_tasks/req186contrato1.json")
                      .read_text())["task_spec"]
    spec = dict(spec, write_path_patterns=[PATH],
                context_path_patterns=spec["context_path_patterns"],
                protected_path_patterns=["pilot/**", "vendor/**"],
                task_id="LF-WORKER-NATIVE-FIXTURE19")
    source.write_bytes(canonical({"task_spec": spec}))
    request = {"schema_version": "CP34_NATIVE_PROPOSAL_REQUEST_V1",
               "task_name": TASK, "branch": "lf/native-proposal/" + TASK,
               "task_pack_sha256": "a" * 64,
               "task_spec_path": "pilot/worker_v08/native_tasks/" + TASK + ".json",
               "task_pack_path": f"pilot/runs/{REQUEST}/proposal_requests/{TASK}.task-pack.json",
               "production_authority": False, "model_invoked": False,
               "merge_authorized": False}
    published = enrich_request(request, spec)
    proposal_request = request_folder / "proposal_requests" / (TASK + ".proposal-request.json")
    proposal_request.parent.mkdir()
    proposal_request.write_bytes(canonical(published))
    git(root, "add", ".")
    git(root, "commit", "-m", "Trusted route registration",
        env={**__import__("os").environ,
             "GIT_AUTHOR_EMAIL": BOT, "GIT_COMMITTER_EMAIL": BOT,
             "GIT_AUTHOR_NAME": "github-actions[bot]",
             "GIT_COMMITTER_NAME": "github-actions[bot]"})
    main = git(root, "rev-parse", "HEAD")
    git(root, "switch", "-c", "lf/native-proposal/" + TASK)
    return root, main, published, spec


def test_published_request_alone_builds_valid_envelope_for_guard_and_worker(tmp_path):
    root, main, request, spec = setup_repo(tmp_path)
    info = json.loads((root / "pilot/runs" / REQUEST / "proposal_requests" /
                       (TASK + ".proposal-request.json")).read_text())["submission"]
    assert info["envelope_path"] == "pilot/native_proposals/" + TASK + ".json"
    assert info["envelope_fields_exact"] == [
        "task_pack_sha256", "proposal_sha256", "proposal", "author"]
    proposal = info["proposal_example"]
    assert set(proposal) == {"schema_version", "summary", "patch", "changed_paths"}
    parsed = parse_patch_proposal(proposal, parse_worker_task(spec))
    facts = inspect_patch(parsed, parse_worker_task(spec))
    assert facts.changed_paths == (PATH,)
    value = {
        "task_pack_sha256": request["task_pack_sha256"],
        "proposal_sha256": hashlib.sha256(canonical(proposal)).hexdigest(),
        "proposal": proposal,
        "author": "GPT_NATIVE",
    }
    envelope = root / info["envelope_path"]
    envelope.parent.mkdir(parents=True)
    envelope.write_bytes(canonical(value))
    git(root, "add", info["envelope_path"])
    git(root, "commit", "-m", "Single native envelope")
    head = git(root, "rev-parse", "HEAD")
    checked = validate_proposal_only(root, head, main_sha=main,
                                     branch="lf/native-proposal/" + TASK)
    assert checked["scope_valid"] and checked["proposal_path"] == info["envelope_path"]
    assert read_proposal_envelope(envelope) == value
    # The client validates the exact registered task-pack binding in addition
    # to the envelope schema; use only synthetic model inputs.
    from native_capture_client import task_pack_sha256
    from programming_agent_runner.model_client import ModelResponse
    instruction, payload = "synthetic native", {"task": "fixture"}
    value["task_pack_sha256"] = task_pack_sha256(instruction, payload)
    envelope.write_bytes(canonical(value))
    response = NativeProposalClient(envelope).generate(instruction, payload)
    assert isinstance(response, ModelResponse)
    assert json.loads(response.output_text) == proposal


@pytest.mark.parametrize("suspended", [False, True])
def test_source_code_direct_push_reports_scope_failure_and_issue_comment(tmp_path, suspended):
    root, main, request, _spec = setup_repo(tmp_path)
    bad = root / PATH
    bad.parent.mkdir(parents=True)
    bad.write_text("openapi: 3.0.3\n")
    git(root, "add", PATH)
    git(root, "commit", "-m", "Wrong direct source push")
    head = git(root, "rev-parse", "HEAD")
    with pytest.raises(ProposalPushBlocked, match="NATIVE_PUSH_SCOPE_INVALID"):
        validate_proposal_only(root, head, main_sha=main,
                               branch="lf/native-proposal/" + TASK)
    real = notifier.command
    comments = []
    from pilot.orchestrator.lifecycle_test_support import fake_api
    reader = fake_api({REQUEST: {"state": "SUSPENDING", "authorization_pr": 77}} if suspended else {})
    def command(*args):
        if args[:2] == ("gh", "api"):
            if args[-1].endswith("/issues/901"):
                return json.dumps({"number": 901, "state": "open",
                                   "labels": [{"name": "lf-request"}]})
            if args[-1].endswith("/comments?per_page=100"):
                return "[]"
            return json.dumps(reader(args[-1].split("/", 2)[2]))
        if args[:3] == ("gh", "issue", "comment"):
            comments.append(args)
            return ""
        return real(*args)
    with patch.object(notifier, "command", side_effect=command):
        assert notifier.notify(root, "lf/native-proposal/" + TASK, head,
                      "NATIVE_PUSH_SCOPE_INVALID") == ("REQUEST_SUSPENDED" if suspended else "NATIVE_PUSH_ALERT_COMMENTED")
    if suspended:
        assert comments == []
        return
    assert len(comments) == 1
    assert "NATIVE_PUSH_SCOPE_INVALID" in comments[0][-1]
    assert "pilot/native_proposals/" + TASK + ".json" in comments[0][-1]
    assert "--label" not in comments[0]


def test_metadata_only_upgrade_preserves_existing_pack_and_registered_task(tmp_path):
    root, main, request, spec = setup_repo(tmp_path)
    rel = f"pilot/runs/{REQUEST}/proposal_requests/{TASK}.proposal-request.json"
    old = dict(request)
    old.pop("submission")
    (root / rel).write_bytes(canonical(old))
    pack = root / f"pilot/runs/{REQUEST}/proposal_requests/{TASK}.task-pack.json"
    pack.write_text("{}")
    # Validate SHA against actual package: no task_pack_sha rewrite permitted.
    from pilot.orchestrator.task_pack_publication import verify_published_pair
    raw = pack.read_bytes()
    old["task_pack_sha256"] = hashlib.sha256(raw).hexdigest()
    (root / rel).write_bytes(canonical(old))
    before_pack, before_task = raw, (root / f"pilot/worker_v08/native_tasks/{TASK}.json").read_bytes()
    git(root, "add", ".")
    git(root, "commit", "-m", "Old published metadata")
    main = git(root, "rev-parse", "HEAD")
    git(root, "switch", "main")
    git(root, "merge", "--ff-only", "lf/native-proposal/" + TASK)
    from pilot.orchestrator import chain_lots
    with patch.object(chain_lots, "ROOT", root), \
         patch.object(chain_lots, "pending_draft", return_value=False), \
         patch.object(chain_lots, "run", return_value=""), \
         patch.object(chain_lots, "worktree", side_effect=lambda sha, br, fn: fn(root)), \
         patch.object(chain_lots, "draft", return_value={"draft_pr":"https://example.invalid/pr"}) as draft:
        result = chain_lots.publish_legacy_submission_contract(REQUEST, TASK, main)
    assert result["status"] == "SUBMISSION_CONTRACT_DRAFT"
    assert draft.call_args.args[3] == [rel]
    assert pack.read_bytes() == before_pack
    assert (root / f"pilot/worker_v08/native_tasks/{TASK}.json").read_bytes() == before_task


def test_trigger_covers_all_proposal_branch_pushes_without_path_filter():
    import yaml
    data = yaml.safe_load((ROOT / ".github/workflows/worker-native-trigger.yml").read_text())
    event = data.get("on", data.get(True))["push"]
    assert event["branches"] == ["lf/native-proposal/**"]
    assert "paths" not in event and "paths-ignore" not in event
    assert data["permissions"]["issues"] == "write"
