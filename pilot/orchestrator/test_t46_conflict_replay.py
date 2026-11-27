"""T46: typed recovery and canonical CP3.5 replay (offline, no GitHub)."""
import json
from unittest.mock import patch

import pytest

from pilot.orchestrator import chain_lots
from pilot.orchestrator.lifecycle_test_support import content, CONTROL
from pilot.orchestrator.conflict_integration_replay import recover, ReplayBlocked

REPO = chain_lots.REPO
MAIN = "a" * 40
SHA = "b" * 40
RUN_ID = 44167628590
TASK = "req286backend2"
BRANCH = f"lf/native-integration/{TASK}-run-{RUN_ID}"
ROW = {"number": 314, "sha": SHA, "branch": BRANCH,
       "kind": "integration", "reason": "GitHub mergeable_state=dirty"}


def transport(*, unresolved=False, existing=False, pending=False, failing=False):
    commands = []

    def run(*args, **kwargs):
        commands.append(args)
        if args[:3] == ("gh", "pr", "list"):
            return json.dumps([{
                "number": 319, "headRefName": BRANCH,
                "author": {"login": "github-actions[bot]"},
            }] if existing else [])
        if args[:3] == ("gh", "workflow", "run"):
            if failing:
                chain_lots.deny("COMMAND_FAILED:gh:STDERR_REDACTED")
            return ""
        raise AssertionError(args)

    def api(path):
        if path == f"contents/{CONTROL}?ref=main":
            return content({})
        if path == "issues/286":
            return {"number": 286, "state": "open"}
        if path == f"actions/runs/{RUN_ID}":
            return {"created_at": "2026-11-17T10:00:00Z", "id": RUN_ID, "status": "completed",
                    "conclusion": "failure" if unresolved else "success",
                    "run_attempt": 1, "event": "workflow_run",
                    "head_branch": "main",
                    "repository": {"full_name": REPO},
                    "path": ".github/workflows/worker-native.yml",
                    "display_title": f"lf-native-auto-lf/native-proposal/{TASK}-" + SHA}
        if path == f"actions/runs/{RUN_ID}/jobs?per_page=100":
            return {"jobs": [{"name": "native", "conclusion": "success"}]}
        if path.startswith("actions/workflows/native-verified-integration.yml/runs?"):
            return {"total_count": 1 if pending else 0, "workflow_runs": [{
                "id": 9999, "event": "workflow_dispatch", "status": "in_progress",
                "display_title": f"CP3.5 recovery native-run-{RUN_ID}",
                "head_branch": "main",
                "path": ".github/workflows/native-verified-integration.yml",
                "repository": {"full_name": REPO},
            }] if pending else []}
        raise AssertionError(path)

    return run, api, commands


def test_t46_retired_backend_extend_pass_three_uses_cp35():
    run, api, calls = transport()
    outcome = recover(ROW, run, api, REPO)
    assert outcome["status"] == "CONFLICT_INTEGRATION_REDISPATCHED"
    assert outcome["source_run_id"] == RUN_ID
    assert any(x[:3] == ("gh", "workflow", "run")
               and "source_run_id=" + str(RUN_ID) in x for x in calls)
    assert not any(x[0] in ("git", "python3") for x in calls)


def test_t46_unresolved_native_pass_is_typed_and_never_dispatched():
    run, api, calls = transport(unresolved=True)
    with pytest.raises(ReplayBlocked, match="^CONFLICT_RECOVERY_SOURCE_RUN_UNRESOLVED$"):
        recover(ROW, run, api, REPO)
    assert not any(x[:3] == ("gh", "workflow", "run") for x in calls)


@pytest.mark.parametrize("existing,pending", [(True, False), (False, True)])
def test_t46_open_integration_or_pending_dispatch_is_idempotent(existing, pending):
    run, api, calls = transport(existing=existing, pending=pending)
    outcome = recover(ROW, run, api, REPO)
    assert outcome["source_run_id"] == RUN_ID
    assert outcome["status"] in ("CONFLICT_INTEGRATION_ALREADY_PUBLISHED",
                                "CONFLICT_INTEGRATION_DISPATCH_PENDING")
    assert not any(x[:3] == ("gh", "workflow", "run") for x in calls)


def test_t46_unsafe_source_and_command_preserves_machine_code():
    run, api, _ = transport(failing=True)
    with patch.object(chain_lots, "run", side_effect=run), \
         patch.object(chain_lots, "api", side_effect=api), \
         patch.object(chain_lots, "conflicted_request", return_value="req-286"):
        with pytest.raises(chain_lots.ChainBlocked) as captured:
            chain_lots.regenerate_conflicted(ROW, MAIN, [])
    code = chain_lots.safe_failure_code(captured.value)
    assert code == "CP36_COMMAND_FAILED:gh:STDERR_REDACTED"
    blocked = chain_lots.sweep_recovery_block("CONFLICT_RECOVERY", captured.value, pr=314)
    assert blocked["reason"] == code
    assert blocked["code"] == code
    assert blocked["pr"] == 314
    assert blocked["phase"] == "CONFLICT_RECOVERY"
    assert blocked["step"] == "gh"


def test_t46_kept_remains_terminal_and_other_recoveries_still_run():
    kept = {"status": "KEPT", "pr": 314, "branch": BRANCH,
            "sha": SHA, "reason": "CONFLICT_ONLY_GENERATED_CHANGES_INDEX"}
    with patch.object(chain_lots, "check_main", return_value=MAIN), \
         patch.object(chain_lots, "main_ci_decision", return_value="GREEN"), \
         patch.object(chain_lots, "retire_conflicted_generated",
                      return_value=[kept]), \
         patch.object(chain_lots, "plans", return_value=[]), \
         patch.object(chain_lots, "retry_failed_bot_prs",
                      return_value=[{"status": "OTHER_RECOVERY_RAN"}]), \
         patch.object(chain_lots, "retry_native_infra", return_value=[]), \
         patch.object(chain_lots, "recover_native_feedback", return_value=[]), \
         patch.object(chain_lots, "recover_route_defects", return_value=[]), \
         patch.object(chain_lots, "regenerate_conflicted",
                      side_effect=AssertionError("KEPT regenerated")):
        outcomes = chain_lots.process(sweep=True, base_sha=MAIN)
    assert kept in outcomes
    assert {"status": "OTHER_RECOVERY_RAN"} in outcomes
