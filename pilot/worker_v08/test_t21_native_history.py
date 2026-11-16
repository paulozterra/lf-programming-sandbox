"""T21: the native history gate recognizes only a SHA-bound infra retry."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_run_history import _recognized_run

TASK = "synthetic1"
SHA = "a" * 40


def test_recovery_run_name_requires_exact_task_and_sha_and_attempt_one():
    candidate = {"head_branch": "main", "run_attempt": 1,
                 "event": "workflow_dispatch",
                 "display_title": f"lf-native-infra-retry-{TASK}-{SHA}"}
    assert _recognized_run(candidate, TASK, attempt=1, sha=SHA)
    assert not _recognized_run(candidate, TASK, attempt=2, sha=SHA)
    assert not _recognized_run(candidate, TASK, attempt=1, sha="b" * 40)
    assert not _recognized_run(candidate, "other", attempt=1, sha=SHA)
    assert not _recognized_run({**candidate, "head_branch": "proposal"},
                               TASK, attempt=1, sha=SHA)


def test_original_manual_and_automatic_run_names_still_work():
    normal = {"head_branch": "main", "run_attempt": 1, "event": "workflow_dispatch",
              "display_title": f"lf-native-{TASK}-a1"}
    automatic = {"head_branch": "main", "run_attempt": 1, "event": "workflow_run",
                 "display_title": f"lf-native-auto-lf/native-proposal/{TASK}-{SHA}"}
    assert _recognized_run(normal, TASK, attempt=1)
    assert _recognized_run(automatic, TASK, sha=SHA)
