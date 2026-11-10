"""GitHub-run-backed attempt admission; history is never read from a proposal branch.

Only runs with a unique, valid Actions-produced proof consume attempts.
Runs stopped before a proof exists are ignored; tampered or duplicated proofs block.
"""
from __future__ import annotations

import io
import json
import os
import re
import urllib.request
import urllib.error
import urllib.parse
import zipfile
from pathlib import Path

from native_attempt_guard import validate_attempt_history

_SHA40 = re.compile(r"[0-9a-f]{40}\Z")
_MANUAL_TITLE = re.compile(r"lf-native-([a-z][a-z0-9_-]{0,31})-a([1-3])\Z")
_AUTO_TITLE = re.compile(r"lf-native-auto-lf/native-proposal/([a-z][a-z0-9_-]{0,31})-([0-9a-f]{40})\Z")
_TASK = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
_WORKFLOW = "worker-native.yml"
_ARTIFACT = "native-attempt-proof"

def _api(base: str, token: str, route: str) -> dict:
    url = f"https://api.github.com/repos/{base}/{route}"
    request = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.loads(response.read(5_000_001))


def _artifact_json(base: str, token: str, run_id: int) -> dict | None:
    obj = _api(base, token, f"actions/runs/{run_id}/artifacts?per_page=100")
    items = obj.get("artifacts")
    if not isinstance(items, list) or obj.get("total_count", len(items)) > 100:
        raise ValueError("NATIVE_PRIOR_ARTIFACT_LIST_INCOMPLETE")
    matches = [a for a in items if a.get("name") == _ARTIFACT]
    if not matches:
        return None  # Preflight/checkout failure is not an attempt.
    if (len(matches) != 1 or matches[0].get("expired") or
        matches[0].get("workflow_run", {}).get("id", run_id) != run_id):
        raise ValueError("NATIVE_PRIOR_PROOF_DUPLICATE_OR_EXPIRED")
    # GitHub artifact API redirects to signed storage. Strip GitHub credentials
    # before requesting the signed URL (Azure rejects forwarded Authorization).
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, request, fp, code, msg, headers, newurl):
            return None

    url = matches[0].get("archive_download_url")
    parsed = urllib.parse.urlsplit(url) if isinstance(url, str) else None
    if parsed is None or parsed.scheme != "https" or parsed.hostname != "api.github.com":
        raise ValueError("NATIVE_PRIOR_PROOF_API_URL_INVALID")
    request = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    })
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=25):
            raise ValueError("NATIVE_PRIOR_PROOF_REDIRECT_EXPECTED")
    except urllib.error.HTTPError as exc:
        if exc.code != 302:
            raise
        location = exc.headers.get("Location")
        exc.close()
    target = urllib.parse.urlsplit(location) if isinstance(location, str) else None
    if (target is None or target.scheme != "https" or not target.hostname
            or target.username is not None or target.password is not None):
        raise ValueError("NATIVE_PRIOR_PROOF_REDIRECT_HTTPS_REQUIRED")
    # A separate request to signed storage: absolutely no Authorization header.
    # Do not follow a second redirect to an unverified destination.
    with urllib.request.build_opener(NoRedirect()).open(
        urllib.request.Request(location), timeout=25
    ) as response:
        archive = response.read(1_000_001)
    if len(archive) > 1_000_000:
        raise ValueError("NATIVE_PRIOR_PROOF_ARCHIVE_SIZE_INVALID")
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        if zipped.namelist() != ["attempt-proof.json"]:
            raise ValueError("NATIVE_PRIOR_PROOF_ARCHIVE_INVALID")
        raw = zipped.read("attempt-proof.json")
        if len(raw) > 4096:
            raise ValueError("NATIVE_PRIOR_PROOF_SIZE_INVALID")
    return json.loads(raw)


def _recognized_run(run: dict, task: str, *, attempt: int | None = None,
                    sha: str | None = None, branch: str | None = None) -> bool:
    if run.get("head_branch") != "main" or run.get("run_attempt") != 1:
        return False
    title = run.get("display_title") or ""
    event = run.get("event")
    if event == "workflow_dispatch":
        match = _MANUAL_TITLE.fullmatch(title)
        return (match is not None and match.group(1) == task and
                (attempt is None or int(match.group(2)) == attempt))
    if event == "workflow_run":
        match = _AUTO_TITLE.fullmatch(title)
        return (match is not None and match.group(1) == task and
                (sha is None or match.group(2) == sha) and
                (branch is None or branch == "lf/native-proposal/" + task))
    return False


def admit_attempt(
    *, repository: str, token: str, task: str, attempt: int | None,
    run_id: int, run_attempt: int, sha: str, output: Path,
    event: str = "workflow_dispatch", head_branch: str = "main",
    proposal_branch: str | None = None, github_output: Path | None = None,
) -> int:
    if (repository != "paulozterra/lf-programming-sandbox" or
        not token or _TASK.fullmatch(task or "") is None or
        (attempt is not None and (type(attempt) is not int or not 1 <= attempt <= 3)) or
        type(run_id) is not int or run_id <= 0 or run_attempt != 1 or
        not isinstance(sha, str) or _SHA40.fullmatch(sha) is None or
        event not in ("workflow_run", "workflow_dispatch") or head_branch != "main" or
        (event == "workflow_run" and
         (attempt is not None or proposal_branch != "lf/native-proposal/" + task)) or
        (event == "workflow_dispatch" and attempt is None)):
        raise ValueError("NATIVE_ADMISSION_INPUT_INVALID")
    results: list[dict] = []
    for page in range(1, 11):
        obj = _api(repository, token,
                   f"actions/workflows/{_WORKFLOW}/runs?per_page=100&page={page}")
        if obj.get("total_count", 0) > 1000 or not isinstance(obj.get("workflow_runs"), list):
            raise ValueError("NATIVE_HISTORY_UNBOUNDED")
        results.extend(obj["workflow_runs"])
        if len(results) >= obj["total_count"]:
            break
    else:
        raise ValueError("NATIVE_HISTORY_INCOMPLETE")
    current = [r for r in results if r.get("id") == run_id]
    if (len(current) != 1 or current[0].get("event") != event or
        not _recognized_run(current[0], task, attempt=attempt,
                            sha=sha if event == "workflow_run" else None,
                            branch=proposal_branch)):
        raise ValueError("NATIVE_CURRENT_RUN_NOT_ATTESTED")
    prior: list[dict] = []
    for run in results:
        if run.get("id") == run_id:
            continue
        # The run title/branch must match the requested task BEFORE download.
        if not _recognized_run(run, task):
            continue
        proof = _artifact_json(repository, token, run["id"])
        if proof is None:
            continue
        if (run["id"] >= run_id or run.get("status") != "completed" or
            not isinstance(proof, dict) or
            set(proof) != {"task_id", "attempt", "task_pack_sha256", "run_id"} or
            proof["run_id"] != run["id"] or
            type(proof["attempt"]) is not int or
            _TASK.fullmatch(proof.get("task_id") or "") is None or
            not _recognized_run(run, proof["task_id"], attempt=proof["attempt"]
                                if run.get("event") == "workflow_dispatch" else None)):
            raise ValueError("NATIVE_PRIOR_PROOF_MISMATCH")
        if proof["task_id"] != task:
            continue
        if run.get("event") == "workflow_run":
            match = _AUTO_TITLE.fullmatch(run.get("display_title") or "")
            if match is not None and match.group(2) == sha:
                raise ValueError("NATIVE_DUPLICATE_PROPOSAL_SHA")
        prior.append(proof)
    computed = len(prior) + 1
    if computed > 3:
        raise ValueError("NATIVE_ATTEMPT_LIMIT_EXCEEDED")
    if attempt is not None and attempt != computed:
        raise ValueError("NATIVE_ATTEMPT_COUNT_MISMATCH")
    prior.sort(key=lambda entry: entry["attempt"])
    validate_attempt_history(task, computed, prior)
    result = {"prior_run_ids": [x["run_id"] for x in prior],
              "run_id": run_id, "attempt": computed,
              "proposal_commit_sha": sha, "event": event}
    output.write_text(json.dumps(result, sort_keys=True) + "\n", encoding="utf-8")
    if github_output is not None:
        with github_output.open("a", encoding="utf-8") as stream:
            stream.write(f"attempt={computed}\n")
    return computed

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True)
    parser.add_argument("--attempt", type=int)
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--out", type=Path, required=True)
    a = parser.parse_args()
    admit_attempt(repository=os.environ["GITHUB_REPOSITORY"],
                  token=os.environ["GITHUB_TOKEN"], task=a.task,
                  attempt=a.attempt, run_id=int(os.environ["GITHUB_RUN_ID"]),
                  run_attempt=int(os.environ["GITHUB_RUN_ATTEMPT"]),
                  sha=a.sha, output=a.out,
                  event=os.environ.get("GITHUB_EVENT_NAME", "workflow_dispatch"),
                  head_branch=os.environ.get("GITHUB_REF_NAME", "main"),
                  proposal_branch=os.environ.get("NATIVE_PROPOSAL_BRANCH"),
                  github_output=a.github_output)


if __name__ == "__main__":
    main()
