"""Protect actual GitHub workflow_run.name/run-name contract and identity gates."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def test_actual_trigger_run_name_matches_privileged_gate():
    trigger=(ROOT/".github/workflows/worker-native-trigger.yml").read_text(encoding="utf-8")
    executor=(ROOT/".github/workflows/worker-native.yml").read_text(encoding="utf-8")
    assert "run-name: lf-native-trigger" in trigger
    assert 'test "$TRIGGER_NAME" = "lf-native-trigger"' in executor
    assert 'TRIGGER_NAME: ${{ github.event.workflow_run.name }}' in executor

def test_other_identity_gates_remain_fail_closed():
    executor=(ROOT/".github/workflows/worker-native.yml").read_text(encoding="utf-8")
    for rule in (
        'test "$TRIGGER_EVENT" = "push"',
        'test "$TRIGGER_CONCLUSION" = "success"',
        'test "$TRIGGER_REPO" = "$REPO_NAME"',
        'TRIGGER_PATH: ${{ github.event.workflow_run.path }}',
        'TRIGGER_SHA: ${{ github.event.workflow_run.head_sha }}',
        'TRIGGER_BRANCH: ${{ github.event.workflow_run.head_branch }}',
        'native_proposal_push_guard.py',
        'NATIVE_PROPOSAL_BRANCH:',
    ):
        assert rule in executor, rule
    assert "\n  push:" not in executor
