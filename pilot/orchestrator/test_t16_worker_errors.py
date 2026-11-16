"""T16: CP3.6 preserves bounded machine error codes, never stderr secrets."""
from __future__ import annotations
import subprocess
from unittest.mock import patch

import pytest

from pilot.orchestrator import chain_lots


def test_prepare_native_error_is_visible():
    command = subprocess.CompletedProcess([], 1, "",
        "other line\nCP35_BLOCKED:CP34_TEMPLATE_INVALID:INSPECT_BRANCH_BEFORE_RETRY\n")
    with patch.object(chain_lots.subprocess, "run", return_value=command):
        with pytest.raises(ValueError, match=r"COMMAND_FAILED:prepare_native_lot.py:CP35_BLOCKED:CP34_TEMPLATE_INVALID"):
            chain_lots.run("python3", "pilot/orchestrator/prepare_native_lot.py")


def test_arbitrary_secret_stderr_is_not_leaked():
    command = subprocess.CompletedProcess([], 1, "",
        "Authorization: Bearer ghp_hidden-secret-string\n")
    with patch.object(chain_lots.subprocess, "run", return_value=command):
        with pytest.raises(ValueError, match=r"COMMAND_FAILED:gh:STDERR_REDACTED") as exc:
            chain_lots.run("gh", "api", "/repo")
    assert "ghp_hidden" not in str(exc.value)


def test_success_returns_stdout():
    command = subprocess.CompletedProcess([], 0, " ok\n", "")
    with patch.object(chain_lots.subprocess, "run", return_value=command):
        assert chain_lots.run("git", "status") == "ok"


# T27 network regressions are exercised by the pre-existing T16 CI job.
# The complete independent suite also lives in test_t27_github_transient.py.
from pilot.orchestrator import test_t27_github_transient as t27


def test_t27_artifact_retries_and_permanent_404():
    t27.test_artifact_502_then_success_allows_normal_result()
    t27.test_artifact_502_persistent_is_named_and_bounded()
    t27.test_artifact_404_is_real_failure_never_retried()
    t27.test_per_request_exception_detail_is_redacted()


def test_t27_api_502_then_success(monkeypatch):
    t27.test_gh_api_502_then_passes(monkeypatch)


def test_t27_main_ci_queued_one_replacement(monkeypatch):
    t27.test_main_ci_queued_redispatch_once(monkeypatch)


def test_t27_workflow_retry_is_bounded():
    t27.test_retry_workflow_bounded_and_structured()
