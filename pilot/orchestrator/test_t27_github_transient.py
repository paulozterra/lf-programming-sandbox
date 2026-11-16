"""T27 offline regression: transient transport, permanent failures, stuck CI.

No real network, GitHub mutations, holdout reads or req-186 writes.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import io
import json
from unittest.mock import patch
import urllib.error

import pytest

from pilot.orchestrator import chain_lots
from pilot.worker_v08.github_network_retry import transport_read


def http_error(code):
    return urllib.error.HTTPError(
        "https://sensitive.invalid/?token=secret", code, "test", {}, io.BytesIO())


def test_artifact_502_then_success_allows_normal_result():
    attempts = []
    sleeps = []

    def download():
        attempts.append(1)
        if len(attempts) == 1:
            raise http_error(502)
        return {"attempt": 1, "proof": "valid"}

    assert transport_read(download, "ARTIFACT_DOWNLOAD",
                          sleep=sleeps.append)["proof"] == "valid"
    assert len(attempts) == 2
    assert sleeps == [1]


def test_artifact_502_persistent_is_named_and_bounded():
    attempts = []
    with pytest.raises(ValueError, match=r"^GITHUB_TRANSITORIO:ARTIFACT_DOWNLOAD$"):
        transport_read(lambda: (attempts.append(1), (_ for _ in ()).throw(http_error(502)))[1],
                       "ARTIFACT_DOWNLOAD", sleep=lambda _: None)
    assert len(attempts) == 3


def test_artifact_404_is_real_failure_never_retried():
    attempts = []

    def missing():
        attempts.append(1)
        raise http_error(404)

    with pytest.raises(ValueError, match=r"^GITHUB_HTTP_404:ARTIFACT_API$"):
        transport_read(missing, "ARTIFACT_API", sleep=lambda _: None)
    assert len(attempts) == 1


def test_per_request_exception_detail_is_redacted():
    assert chain_lots.safe_failure_code(http_error(502)) == "CP36_LOCAL_FAILURE:HTTPError:502"
    assert "sensitive" not in chain_lots.safe_failure_code(http_error(404))
    assert chain_lots.safe_failure_code(ValueError("GITHUB_TRANSITORIO:API")) == "GITHUB_TRANSITORIO:API"


def test_gh_api_502_then_passes(monkeypatch):
    calls = []

    class Completed:
        def __init__(self, code, output="", stderr=""):
            self.returncode, self.stdout, self.stderr = code, output, stderr

    def fake_run(*args, **kwargs):
        calls.append(args)
        return Completed(1, stderr="HTTP 502 Bad Gateway") if len(calls) == 1 else Completed(0, '{"ok":true}')

    monkeypatch.setattr(chain_lots.subprocess, "run", fake_run)
    monkeypatch.setattr(chain_lots.time, "sleep", lambda _: None)
    assert chain_lots.api("issues/1") == {"ok": True}
    assert len(calls) == 2


def test_main_ci_queued_redispatch_once(monkeypatch):
    age = (datetime.now(timezone.utc) - timedelta(minutes=13)).isoformat()
    sha = "a" * 40
    row = dict(head_sha=sha, head_branch="main", event="push",
               path=".github/workflows/ci.yml", repository={"full_name": chain_lots.REPO},
               run_attempt=1, status="queued", created_at=age, id=987)
    commands = []

    def fetch(path):
        if path.endswith("/jobs?per_page=100"):
            return {"jobs": [], "total_count": 0}
        return {"workflow_runs": [row], "total_count": 1}

    monkeypatch.setattr(chain_lots, "api", fetch)
    monkeypatch.setattr(chain_lots, "run", lambda *args, **kw: commands.append(args) or "")
    assert chain_lots.main_ci_decision(sha) == "GITHUB_CI_ATASCADO"
    assert sum("workflow" in call for call in commands) == 1
    row["event"] = "workflow_dispatch"
    commands.clear()
    assert chain_lots.main_ci_decision(sha) == "GITHUB_CI_ATASCADO"
    assert not commands


def test_retry_workflow_bounded_and_structured():
    from pathlib import Path
    path = Path(__file__).resolve().parents[2] / ".github/workflows/chain-lots.yml"
    text = path.read_text("utf-8")
    assert "retry_attempt:" in text
    assert 'sleep 180' in text
    assert '"$RETRY_ATTEMPT" -lt 2' in text
    assert 'row["reason"].startswith("GITHUB_TRANSITORIO:")' in text
    assert "request-failure-watchdog.yml" in text
