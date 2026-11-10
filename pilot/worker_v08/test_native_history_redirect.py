"""Offline signed GitHub artifact transport and pre-download task isolation tests."""
from __future__ import annotations

import io
import json
import urllib.error
import zipfile
from email.message import Message
from unittest.mock import patch

import pytest

import native_run_history as history


def archive(proof: dict) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as file:
        file.writestr("attempt-proof.json", json.dumps(proof))
    return output.getvalue()


class FakeResponse:
    def __init__(self, content: bytes):
        self.content = content
    def read(self, limit: int = -1) -> bytes:
        return self.content[:limit] if limit >= 0 else self.content
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False


def test_signed_storage_redirect_sends_token_only_to_github():
    proof = {"task_id": "ex7", "attempt": 1,
             "task_pack_sha256": "a" * 64, "run_id": 123}
    target = "https://signed.blob.core.windows.net/object?sig=opaque"
    api = "https://api.github.com/repos/paulozterra/lf-programming-sandbox/actions/artifacts/999/zip"
    seen = []

    class FakeOpener:
        def open(self, request, timeout):
            seen.append(request)
            if len(seen) == 1:
                headers = Message()
                headers["Location"] = target
                raise urllib.error.HTTPError(api, 302, "Found", headers, None)
            assert len(seen) == 2
            return FakeResponse(archive(proof))

    def fake_api(base, token, route):
        assert token == "offline-secret"
        return {"total_count": 1, "artifacts": [
            {"name": "native-attempt-proof", "expired": False,
             "archive_download_url": api, "workflow_run": {"id": 123}}]}

    with patch.object(history, "_api", side_effect=fake_api), patch.object(
        history.urllib.request, "build_opener", side_effect=lambda *handlers: FakeOpener()
    ) as opener:
        result = history._artifact_json("paulozterra/lf-programming-sandbox", "offline-secret", 123)

    assert result == proof
    assert opener.call_count == 2
    assert all(isinstance(call.args[0], history.urllib.request.HTTPRedirectHandler)
               for call in opener.call_args_list)
    assert seen[0].full_url == api
    assert seen[0].get_header("Authorization") == "Bearer offline-secret"
    assert seen[1].full_url == target
    assert seen[1].get_header("Authorization") is None
    assert not seen[1].has_header("Authorization")


@pytest.mark.parametrize("target", [
    "http://signed.blob.core.windows.net/zip",
    "file:///etc/passwd",
    "//signed.blob.core.windows.net/zip",
    "https://",
    "https://username:password@storage.example/blob",
])
def test_untrusted_redirect_location_fails_closed(target):
    api = "https://api.github.com/repos/paulozterra/lf-programming-sandbox/actions/artifacts/999/zip"
    calls = []
    class FakeOpener:
        def open(self, request, timeout):
            calls.append(request)
            headers = Message()
            headers["Location"] = target
            raise urllib.error.HTTPError(api, 302, "Found", headers, None)
    with patch.object(history, "_api", return_value={"total_count": 1, "artifacts": [
        {"name": "native-attempt-proof", "expired": False,
         "archive_download_url": api, "workflow_run": {"id": 123}}]}), patch.object(
             history.urllib.request, "build_opener", side_effect=lambda *a: FakeOpener()):
        with pytest.raises(ValueError, match="NATIVE_PRIOR_PROOF_REDIRECT_HTTPS_REQUIRED"):
            history._artifact_json("paulozterra/lf-programming-sandbox", "offline-secret", 123)
    assert len(calls) == 1


def test_ex6_run_skipped_before_any_artifact_lookup_for_ex7(tmp_path):
    current_sha = "b" * 40
    current = {"id": 1200, "event": "workflow_run", "head_branch": "main",
               "run_attempt": 1, "status": "in_progress",
               "display_title": "lf-native-auto-lf/native-proposal/ex7-" + current_sha}
    other = {"id": 1000, "event": "workflow_dispatch", "head_branch": "main",
             "run_attempt": 1, "status": "completed",
             "display_title": "lf-native-ex6-a1"}
    downloaded = []
    with patch.object(history, "_api", return_value={"total_count": 2,
            "workflow_runs": [other, current]}), patch.object(
            history, "_artifact_json", side_effect=lambda *args: downloaded.append(args) or None):
        attempt = history.admit_attempt(
            repository="paulozterra/lf-programming-sandbox",
            token="offline-secret", task="ex7", attempt=None,
            run_id=1200, run_attempt=1, sha=current_sha,
            output=tmp_path / "history.json", event="workflow_run",
            head_branch="main", proposal_branch="lf/native-proposal/ex7")
    assert attempt == 1
    assert downloaded == []


def test_matching_task_artifact_mismatched_task_id_rejected(tmp_path):
    sha = "b" * 40
    old = {"id": 1100, "event": "workflow_dispatch", "head_branch": "main",
           "run_attempt": 1, "status": "completed",
           "display_title": "lf-native-ex7-a1"}
    current = {"id": 1200, "event": "workflow_run", "head_branch": "main",
               "run_attempt": 1, "status": "in_progress",
               "display_title": "lf-native-auto-lf/native-proposal/ex7-" + sha}
    wrong = {"task_id": "ex6", "attempt": 1,
             "task_pack_sha256": "a" * 64, "run_id": 1100}
    with patch.object(history, "_api", return_value={"total_count": 2,
            "workflow_runs": [old, current]}), patch.object(
            history, "_artifact_json", return_value=wrong) as downloaded:
        with pytest.raises(ValueError, match="NATIVE_PRIOR_PROOF_MISMATCH"):
            history.admit_attempt(
                repository="paulozterra/lf-programming-sandbox",
                token="offline-secret", task="ex7", attempt=None,
                run_id=1200, run_attempt=1, sha=sha,
                output=tmp_path / "history.json", event="workflow_run",
                head_branch="main", proposal_branch="lf/native-proposal/ex7")
    downloaded.assert_called_once()
