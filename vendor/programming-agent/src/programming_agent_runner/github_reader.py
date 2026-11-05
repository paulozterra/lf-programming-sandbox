from __future__ import annotations

import io
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from typing import Any, Protocol

from .hashutil import sha256_bytes, strict_json_loads
from .structured_test_receipt import (
    STRUCTURED_TEST_RECEIPT_FILENAME,
    nonpass_test_ids,
    successful_test_ids,
    validate_structured_test_receipt,
)


EXECUTED_HEAD_RECEIPT = re.compile(r"\bEXECUTED_HEAD_SHA=([0-9a-f]{40})\b")
MAX_ARTIFACT_ARCHIVE_BYTES = 10 * 1024 * 1024
MAX_RECEIPT_BYTES = 5 * 1024 * 1024


class GitHubReadClient(Protocol):
    def resolve_ref(self, repo_full_name: str, ref: str) -> str: ...

    def source_tree(self, repo_full_name: str, head_sha: str) -> dict[str, Any]: ...

    def combined_status(self, repo_full_name: str, head_sha: str) -> dict[str, Any]: ...

    def workflow_runs(self, repo_full_name: str, head_sha: str) -> dict[str, Any]: ...

    def check_runs(self, repo_full_name: str, head_sha: str) -> dict[str, Any]: ...


class GitHubReadError(RuntimeError):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass
class GitHubReader:
    token: str
    api_base: str = "https://api.github.com"

    @classmethod
    def from_environment(cls) -> "GitHubReader | None":
        token = os.environ.get("GITHUB_TOKEN")
        return cls(token) if token else None

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "programming-agent-runner/0.5",
        }

    def _get(self, path: str) -> Any:
        request = urllib.request.Request(
            self.api_base.rstrip("/") + path,
            headers=self._headers(),
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
            raise GitHubReadError(str(exc)) from exc

    def _redirected_bytes(self, path: str, *, maximum_bytes: int) -> bytes:
        request = urllib.request.Request(
            self.api_base.rstrip("/") + path,
            headers=self._headers(),
        )
        opener = urllib.request.build_opener(_NoRedirect)
        location: str | None = None
        try:
            with opener.open(request, timeout=20) as response:
                if response.status == 200:
                    data = response.read(maximum_bytes + 1)
                    if len(data) > maximum_bytes:
                        raise GitHubReadError("GitHub response exceeded size limit")
                    return data
                location = response.headers.get("Location")
        except urllib.error.HTTPError as exc:
            if exc.code not in {301, 302, 303, 307, 308}:
                raise GitHubReadError(str(exc)) from exc
            location = exc.headers.get("Location")
        except urllib.error.URLError as exc:
            raise GitHubReadError(str(exc)) from exc

        if not location:
            raise GitHubReadError("GitHub download response did not contain redirect location")
        parsed_location = urllib.parse.urlparse(location)
        if parsed_location.scheme != "https" or not parsed_location.hostname:
            raise GitHubReadError("GitHub download redirect must use an absolute HTTPS URL")

        signed_request = urllib.request.Request(
            location,
            headers={"User-Agent": "programming-agent-runner/0.5"},
        )
        try:
            with urllib.request.urlopen(signed_request, timeout=20) as response:
                data = response.read(maximum_bytes + 1)
                if len(data) > maximum_bytes:
                    raise GitHubReadError("GitHub redirected response exceeded size limit")
                return data
        except (urllib.error.URLError, urllib.error.HTTPError) as exc:
            raise GitHubReadError(str(exc)) from exc

    def _job_log_text(self, repo_full_name: str, job_id: int) -> str:
        data = self._redirected_bytes(
            f"/repos/{repo_full_name}/actions/jobs/{job_id}/logs",
            maximum_bytes=MAX_ARTIFACT_ARCHIVE_BYTES,
        )
        return data.decode("utf-8", errors="replace")

    def _job_metadata(self, repo_full_name: str, job_id: int) -> dict[str, Any]:
        data = self._get(f"/repos/{repo_full_name}/actions/jobs/{job_id}")
        if not isinstance(data, dict):
            raise GitHubReadError("GitHub job response was not an object")
        return data

    def _workflow_artifacts(self, repo_full_name: str, run_id: int) -> dict[str, Any]:
        data = self._get(f"/repos/{repo_full_name}/actions/runs/{run_id}/artifacts?per_page=100")
        if not isinstance(data, dict):
            raise GitHubReadError("GitHub artifacts response was not an object")
        return data

    def _artifact_zip_bytes(self, repo_full_name: str, artifact_id: int) -> bytes:
        return self._redirected_bytes(
            f"/repos/{repo_full_name}/actions/artifacts/{artifact_id}/zip",
            maximum_bytes=MAX_ARTIFACT_ARCHIVE_BYTES,
        )

    @staticmethod
    def _artifact_name(run_id: int, run_attempt: int, head_sha: str) -> str:
        return f"quality-test-receipt-{run_id}-{run_attempt}-{head_sha}"

    @staticmethod
    def _receipt_from_zip(data: bytes) -> dict[str, Any]:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                infos = archive.infolist()
                if len(infos) != 1 or infos[0].filename != STRUCTURED_TEST_RECEIPT_FILENAME:
                    raise GitHubReadError("structured test artifact must contain exactly the canonical receipt file")
                info = infos[0]
                if info.is_dir() or info.file_size > MAX_RECEIPT_BYTES:
                    raise GitHubReadError("structured test receipt has invalid size or type")
                if info.flag_bits & 0x1:
                    raise GitHubReadError("encrypted structured test receipts are forbidden")
                raw = archive.read(info)
        except (zipfile.BadZipFile, KeyError, RuntimeError, OSError) as exc:
            raise GitHubReadError(f"invalid structured test artifact: {exc}") from exc
        try:
            payload = strict_json_loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise GitHubReadError(f"structured test receipt is not valid UTF-8 JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise GitHubReadError("structured test receipt root must be an object")
        return payload

    @staticmethod
    def _empty_structured_receipt(status: str, **extra: Any) -> dict[str, Any]:
        return {
            "test_execution_receipt_status": status,
            "executed_pass_test_ids": [],
            "executed_nonpass_test_ids": [],
            "observed_unittest_result_count": 0,
            "structured_test_receipt": None,
            **extra,
        }

    def _structured_test_receipt(
        self,
        repo_full_name: str,
        job_id: Any,
        head_sha: Any,
    ) -> dict[str, Any]:
        if not isinstance(job_id, int) or not isinstance(head_sha, str):
            return self._empty_structured_receipt("MISSING_JOB_ID")
        try:
            job = self._job_metadata(repo_full_name, job_id)
            run_id = job.get("run_id")
            run_attempt = job.get("run_attempt")
            job_name = job.get("name")
            if type(run_id) is not int or type(run_attempt) is not int or not isinstance(job_name, str):
                return self._empty_structured_receipt("INVALID", structured_test_receipt_errors=["job_metadata_invalid"])
            if job.get("id") != job_id or job.get("head_sha") != head_sha or job_name != "quality":
                return self._empty_structured_receipt(
                    "INVALID",
                    structured_test_receipt_errors=["job_identity_mismatch"],
                )

            artifacts_payload = self._workflow_artifacts(repo_full_name, run_id)
            artifacts = artifacts_payload.get("artifacts")
            total_count = artifacts_payload.get("total_count")
            if not isinstance(artifacts, list):
                return self._empty_structured_receipt("INVALID", structured_test_receipt_errors=["artifact_list_invalid"])
            if isinstance(total_count, int) and total_count > len(artifacts):
                return self._empty_structured_receipt("UNAVAILABLE", structured_test_receipt_errors=["artifact_list_truncated"])

            expected_name = self._artifact_name(run_id, run_attempt, head_sha)
            matches = [
                artifact
                for artifact in artifacts
                if isinstance(artifact, dict)
                and artifact.get("name") == expected_name
                and artifact.get("expired") is not True
            ]
            if not matches:
                return self._empty_structured_receipt("MISSING")
            if len(matches) != 1:
                return self._empty_structured_receipt("AMBIGUOUS")

            artifact = matches[0]
            artifact_id = artifact.get("id")
            artifact_digest = artifact.get("digest")
            if type(artifact_id) is not int:
                return self._empty_structured_receipt("INVALID", structured_test_receipt_errors=["artifact_id_invalid"])
            archive = self._artifact_zip_bytes(repo_full_name, artifact_id)
            actual_digest = f"sha256:{sha256_bytes(archive)}"
            errors: list[str] = []
            if not isinstance(artifact_digest, str):
                errors.append("artifact_digest_missing")
            elif artifact_digest != actual_digest:
                errors.append("artifact_digest_mismatch")

            try:
                receipt = self._receipt_from_zip(archive)
            except GitHubReadError as exc:
                return self._empty_structured_receipt(
                    "INVALID",
                    structured_test_receipt_errors=[str(exc)],
                    artifact_id=artifact_id,
                    artifact_digest=artifact_digest,
                    artifact_archive_sha256=sha256_bytes(archive),
                )
            errors.extend(
                validate_structured_test_receipt(
                    receipt,
                    expected_repository=repo_full_name,
                    expected_head_sha=head_sha,
                    expected_run_id=run_id,
                    expected_run_attempt=run_attempt,
                    expected_job_name=job_name,
                )
            )
            summary = receipt.get("summary")
            if not isinstance(summary, dict) or summary.get("overall_status") != "PASS":
                errors.append("structured_test_overall_nonpass")
            if errors:
                return self._empty_structured_receipt(
                    "INVALID",
                    structured_test_receipt_errors=sorted(set(errors)),
                    artifact_id=artifact_id,
                    artifact_digest=artifact_digest,
                    artifact_archive_sha256=sha256_bytes(archive),
                )

            passed = sorted(successful_test_ids(receipt))
            nonpass = sorted(nonpass_test_ids(receipt))
            return {
                "test_execution_receipt_status": "PRESENT",
                "executed_pass_test_ids": passed,
                "executed_nonpass_test_ids": nonpass,
                "observed_unittest_result_count": len(receipt.get("results") or []),
                "structured_test_receipt": receipt,
                "structured_test_receipt_sha256": receipt.get("receipt_sha256"),
                "artifact_id": artifact_id,
                "artifact_digest": artifact_digest,
                "artifact_archive_sha256": sha256_bytes(archive),
                "run_id": run_id,
                "run_attempt": run_attempt,
                "job_id": job_id,
            }
        except GitHubReadError as exc:
            return self._empty_structured_receipt(
                "UNAVAILABLE",
                structured_test_receipt_errors=[str(exc)],
            )

    def _execution_receipt(self, repo_full_name: str, job_id: Any) -> dict[str, Any]:
        if not isinstance(job_id, int):
            return {
                "executed_head_sha": None,
                "execution_receipt_status": "MISSING_JOB_ID",
                "execution_receipt_values": [],
            }
        try:
            text = self._job_log_text(repo_full_name, job_id)
        except GitHubReadError as exc:
            return {
                "executed_head_sha": None,
                "execution_receipt_status": "UNAVAILABLE",
                "execution_receipt_values": [],
                "execution_receipt_error": str(exc),
            }

        values = sorted(set(EXECUTED_HEAD_RECEIPT.findall(text)))
        return {
            "executed_head_sha": values[0] if len(values) == 1 else None,
            "execution_receipt_status": (
                "PRESENT" if len(values) == 1 else "MISSING" if not values else "AMBIGUOUS"
            ),
            "execution_receipt_values": values,
        }

    def resolve_ref(self, repo_full_name: str, ref: str) -> str:
        encoded = urllib.parse.quote(ref, safe="")
        data = self._get(f"/repos/{repo_full_name}/commits/{encoded}")
        sha = data.get("sha")
        if not isinstance(sha, str):
            raise GitHubReadError("GitHub commit response did not contain sha")
        return sha

    def source_tree(self, repo_full_name: str, head_sha: str) -> dict[str, Any]:
        commit = self._get(f"/repos/{repo_full_name}/git/commits/{head_sha}")
        tree = commit.get("tree") if isinstance(commit, dict) else None
        tree_sha = tree.get("sha") if isinstance(tree, dict) else None
        if not isinstance(tree_sha, str):
            raise GitHubReadError("GitHub commit response did not contain tree sha")
        data = self._get(f"/repos/{repo_full_name}/git/trees/{tree_sha}?recursive=1")
        raw_entries = data.get("tree") if isinstance(data, dict) else None
        if not isinstance(raw_entries, list):
            raise GitHubReadError("GitHub tree response did not contain entries")
        entries = [
            {
                "path": item.get("path"),
                "mode": item.get("mode"),
                "type": item.get("type"),
                "sha": item.get("sha"),
            }
            for item in raw_entries
            if isinstance(item, dict) and item.get("type") != "tree"
        ]
        return {
            "tree_sha": tree_sha,
            "truncated": data.get("truncated"),
            "total_count": len(entries),
            "entries": entries,
        }

    def combined_status(self, repo_full_name: str, head_sha: str) -> dict[str, Any]:
        data = self._get(f"/repos/{repo_full_name}/commits/{head_sha}/status")
        return {
            "state": data.get("state"),
            "total_count": data.get("total_count", len(data.get("statuses", []))),
            "statuses": data.get("statuses", []),
        }

    def workflow_runs(self, repo_full_name: str, head_sha: str) -> dict[str, Any]:
        data = self._get(f"/repos/{repo_full_name}/actions/runs?head_sha={head_sha}&per_page=100")
        runs = data.get("workflow_runs") or []
        return {
            "total_count": data.get("total_count", len(runs)),
            "runs": [
                {
                    "id": run.get("id"),
                    "workflow_id": run.get("workflow_id"),
                    "check_suite_id": run.get("check_suite_id"),
                    "name": run.get("name"),
                    "path": run.get("path"),
                    "event": run.get("event"),
                    "status": run.get("status"),
                    "conclusion": run.get("conclusion"),
                    "head_sha": run.get("head_sha"),
                }
                for run in runs
            ],
        }

    def check_runs(self, repo_full_name: str, head_sha: str) -> dict[str, Any]:
        data = self._get(f"/repos/{repo_full_name}/commits/{head_sha}/check-runs?per_page=100")
        runs = data.get("check_runs") or []
        normalized: list[dict[str, Any]] = []
        for run in runs:
            check_suite_id = (
                run.get("check_suite", {}).get("id")
                if isinstance(run.get("check_suite"), dict)
                else None
            )
            app_slug = (
                run.get("app", {}).get("slug")
                if isinstance(run.get("app"), dict)
                else None
            )
            item: dict[str, Any] = {
                "id": run.get("id"),
                "name": run.get("name"),
                "status": run.get("status"),
                "conclusion": run.get("conclusion"),
                "head_sha": run.get("head_sha"),
                "check_suite_id": check_suite_id,
                "app_slug": app_slug,
            }
            if item["name"] == "quality" and app_slug == "github-actions":
                item.update(self._execution_receipt(repo_full_name, item["id"]))
                item.update(self._structured_test_receipt(repo_full_name, item["id"], item["head_sha"]))
            normalized.append(item)
        return {
            "total_count": data.get("total_count", len(runs)),
            "runs": normalized,
        }
