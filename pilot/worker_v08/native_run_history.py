"""GitHub-run-backed attempt admission; history is never read from a proposal branch.

Only runs with a unique, valid Actions-produced proof consume attempts.
For Workers created after PR #370's merge, absent or expired evidence is
fail-closed unless the job attests NO_ATTEMPT or is provably unstarted.
Pre-merge historical runs preserve old missing/expired behavior unless denied
in the explicit governed exception list.
"""
from __future__ import annotations
# Resolve the trusted repository package for direct script execution.
import sys as _project_sys
from pathlib import Path as _project_Path
_project_sys.path.insert(0, str(_project_Path(__file__).resolve().parents[2]))
from pilot.config.project_config import storage_path, storage

import io
from datetime import datetime, timezone
import json
import os
import re
import urllib.request
import urllib.error
import urllib.parse
import zipfile
from pathlib import Path

from native_attempt_guard import validate_attempt_history
from github_network_retry import transport_read

_SHA40 = re.compile(r"[0-9a-f]{40}\Z")
_MANUAL_TITLE = re.compile(r"lf-native-(?:(req-[1-9][0-9]*)-)?([a-z][a-z0-9_-]{0,31})-a([1-3])(?:-([0-9a-f]{40}))?\Z")
_INFRA_TITLE = re.compile(r"lf-native-infra-retry-([a-z][a-z0-9_-]{0,31})-([0-9a-f]{40})\Z")
_ROUTE_TITLE = re.compile(r"lf-native-route-retry-([a-z][a-z0-9_-]{0,31})-([0-9a-f]{40})\Z")
_PENDING_TITLE = re.compile(r"lf-native-pending-retry-([a-z][a-z0-9_-]{0,31})-([0-9a-f]{40})\Z")
_AUTO_TITLE = re.compile(r"lf-native-auto-lf/native-proposal/([a-z][a-z0-9_-]{0,31})-([0-9a-f]{40})\Z")
_TASK = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
_WORKFLOW = "worker-native.yml"
_ARTIFACT = "native-attempt-proof"
_NO_ATTEMPT_ARTIFACT = "native-no-attempt"
_WORKER_STEP = "Execute original run_verified_worker using native proposal (single attempt)"
# CHG-0249: immutable PR #370 merge metadata is pinned in a trusted,
# versioned file; admission never fetches GET /pulls/370.
# A Worker run created at/after merged_at remains subject to strict proof.
_R3_CUTOVER_FILE = Path(__file__).with_name("r3_cutover.json")
_HISTORIC_EXCEPTIONS = Path(__file__).with_name("r3_historical_proof_exceptions.json")

def _api(base: str, token: str, route: str) -> dict:
    url = f"https://api.github.com/repos/{base}/{route}"
    request = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    def read():
        with urllib.request.urlopen(request, timeout=25) as response:
            return json.loads(response.read(5_000_001))
    return transport_read(read, "ARTIFACT_API")


def _artifact_json(base: str, token: str, run_id: int, *,
                   artifact_name: str = _ARTIFACT, inventory_api=None) -> dict | None:
    # Optional, recovery-only transport injection. The native admission path
    # leaves inventory_api=None and retains its original strict API behavior.
    route = f"actions/runs/{run_id}/artifacts?per_page=100"
    obj = inventory_api(route) if inventory_api is not None else _api(base, token, route)
    items = obj.get("artifacts")
    if not isinstance(items, list) or obj.get("total_count", len(items)) > 100:
        raise ValueError("NATIVE_PRIOR_ARTIFACT_LIST_INCOMPLETE")
    matches = [a for a in items if a.get("name") == artifact_name]
    if not matches:
        return None  # Caller must attest absence; no implicit forgiveness.
    if len(matches) != 1 or matches[0].get("workflow_run", {}).get("id", run_id) != run_id:
        raise ValueError("NATIVE_PRIOR_PROOF_DUPLICATE_OR_EXPIRED")
    if matches[0].get("expired"):
        raise ValueError("NATIVE_PRIOR_PROOF_MISSING")
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
    def read_redirect():
        try:
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=25):
                raise ValueError("NATIVE_PRIOR_PROOF_REDIRECT_EXPECTED")
        except urllib.error.HTTPError as exc:
            if exc.code != 302:
                raise
            location = exc.headers.get("Location")
            exc.close()
            return location

    location = transport_read(read_redirect, "ARTIFACT_REDIRECT")
    target = urllib.parse.urlsplit(location) if isinstance(location, str) else None
    if (target is None or target.scheme != "https" or not target.hostname
            or target.username is not None or target.password is not None):
        raise ValueError("NATIVE_PRIOR_PROOF_REDIRECT_HTTPS_REQUIRED")
    # A separate request to signed storage: absolutely no Authorization header.
    # Do not follow a second redirect to an unverified destination.
    def read_archive():
        with urllib.request.build_opener(NoRedirect()).open(
            urllib.request.Request(location), timeout=25
        ) as response:
            return response.read(1_000_001)

    archive = transport_read(read_archive, "ARTIFACT_DOWNLOAD")
    if len(archive) > 1_000_000:
        raise ValueError("NATIVE_PRIOR_PROOF_ARCHIVE_SIZE_INVALID")
    filename = "attempt-proof.json" if artifact_name == _ARTIFACT else "no-attempt.json"
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        if zipped.namelist() != [filename]:
            raise ValueError("NATIVE_PRIOR_PROOF_ARCHIVE_INVALID")
        raw = zipped.read(filename)
        if len(raw) > 4096:
            raise ValueError("NATIVE_PRIOR_PROOF_SIZE_INVALID")
    return json.loads(raw)


def _r3_merge_cutover(base: str, token: str) -> tuple[str, datetime]:
    """Read the fixed PR #370 historical boundary without any GitHub API call."""
    try:
        document = json.loads(_R3_CUTOVER_FILE.read_text("utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("NATIVE_PROOF_CUTOFF_UNRESOLVED") from exc
    if (not isinstance(document, dict)
            or set(document) != {"schema_version", "pr_number", "merge_commit_sha", "merged_at"}
            or document["schema_version"] != "LF_R3_CUTOVER_V1"
            or type(document["pr_number"]) is not int or document["pr_number"] != 370):
        raise ValueError("NATIVE_PROOF_CUTOFF_UNRESOLVED")
    sha, stamp = document["merge_commit_sha"], document["merged_at"]
    if (not isinstance(sha, str) or _SHA40.fullmatch(sha) is None
            or not isinstance(stamp, str)):
        raise ValueError("NATIVE_PROOF_CUTOFF_UNRESOLVED")
    try:
        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("NATIVE_PROOF_CUTOFF_UNRESOLVED") from exc
    if parsed.tzinfo is None:
        raise ValueError("NATIVE_PROOF_CUTOFF_UNRESOLVED")
    return sha, parsed.astimezone(timezone.utc)


def _r3_historical_exceptions() -> frozenset[int]:
    """Explicit, reviewed exceptions to pre-cutover forgiveness."""
    try:
        document = json.loads(_HISTORIC_EXCEPTIONS.read_text("utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("NATIVE_PROOF_EXCEPTIONS_INVALID") from exc
    entries = document.get("blocked_run_ids") if isinstance(document, dict) else None
    if (not isinstance(document, dict)
            or set(document) != {"schema_version", "blocked_run_ids"}
            or document["schema_version"] != "LF_R3_HISTORIC_PROOF_EXCEPTIONS_V1"
            or not isinstance(entries, list)
            or any(type(item) is not int or item <= 0 for item in entries)
            or len(entries) != len(set(entries))):
        raise ValueError("NATIVE_PROOF_EXCEPTIONS_INVALID")
    return frozenset(entries)


def _r3_pre_cutover(base: str, token: str, run: dict,
                    merge: tuple[str, datetime] | None = None) -> bool:
    """Only runs created strictly before CHG-0248's merged_at are historical.

    When the PR is unmerged or run metadata is missing, fail closed. It
    is never permissible to infer 'historical' from a missing proof alone.
    """
    if type(run.get("id")) is not int or run["id"] <= 0:
        raise ValueError("NATIVE_PRIOR_RUN_DATE_INVALID")
    if run["id"] in _r3_historical_exceptions():
        return False
    _, merged_at = merge if merge is not None else _r3_merge_cutover(base, token)
    stamp = run.get("created_at")
    if not isinstance(stamp, str):
        raise ValueError("NATIVE_PRIOR_RUN_DATE_INVALID")
    try:
        created = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("NATIVE_PRIOR_RUN_DATE_INVALID") from exc
    if created.tzinfo is None:
        raise ValueError("NATIVE_PRIOR_RUN_DATE_INVALID")
    return created.astimezone(timezone.utc) < merged_at


def _no_attempt_attested(base: str, token: str, run: dict, task: str) -> bool:
    """Only the same Actions job can justify an absent attempt proof."""
    run_id = run["id"]
    marker = _artifact_json(base, token, run_id, artifact_name=_NO_ATTEMPT_ARTIFACT)
    if marker is not None:
        return (isinstance(marker, dict)
                and set(marker) == {"schema_version", "task_id", "run_id", "attempt", "reason"}
                and marker["schema_version"] == "LF_NATIVE_NO_ATTEMPT_V1"
                and marker["task_id"] == task and marker["run_id"] == run_id
                and type(marker["attempt"]) is int and 1 <= marker["attempt"] <= 3
                and marker["reason"] in ("PRE_ATTEMPT", "EXAMINER_CONTROL"))
    jobs = _api(base, token, f"actions/runs/{run_id}/jobs?per_page=100")
    rows = jobs.get("jobs")
    # GitHub can cancel a pending run before assigning any job. No executed
    # job exists, hence no attempt can have been spent.
    if (rows == [] and jobs.get("total_count") == 0
            and run.get("conclusion") in ("cancelled", "skipped")):
        return True
    if (not isinstance(rows, list) or jobs.get("total_count") != 1
            or len(rows) != 1 or rows[0].get("name") != "native"):
        return False
    # A job skipped by its own 'if' never executed a Worker step; GitHub
    # often returns an empty steps list (or omits the steps field entirely).
    if rows[0].get("conclusion") == "skipped":
        return True
    steps = rows[0].get("steps")
    if not isinstance(steps, list):
        return False
    worker_steps = [step for step in steps if isinstance(step, dict)
                    and step.get("name") == _WORKER_STEP]
    return (len(worker_steps) == 1 and worker_steps[0].get("status") == "completed"
            and worker_steps[0].get("conclusion") == "skipped")


def _recognized_run(run: dict, task: str, *, attempt: int | None = None,
                    sha: str | None = None, branch: str | None = None,
                    allow_legacy_manual: bool = True) -> bool:
    if run.get("head_branch") != "main" or run.get("run_attempt") != 1:
        return False
    title = run.get("display_title") or ""
    event = run.get("event")
    if event == "workflow_dispatch":
        match = _MANUAL_TITLE.fullmatch(title)
        if match is not None:
            # Resolve a request_slug against the *registered* task identity,
            # not by greedily splitting a title that itself starts req-N.
            bound = re.fullmatch(
                r"lf-native-(?:req-[1-9][0-9]*-)?" + re.escape(task) +
                r"-a([1-3])(?:-([0-9a-f]{40}))?\Z", title)
            return (bound is not None
                    and (attempt is None or int(bound.group(1)) == attempt)
                    and (bound.group(2) is not None or allow_legacy_manual)
                    and (allow_legacy_manual or
                         title == f"lf-native-{task}-a{bound.group(1)}-{bound.group(2)}")
                    and (sha is None or bound.group(2) is None
                         or bound.group(2) == sha))
        recovery = (_INFRA_TITLE.fullmatch(title) or _ROUTE_TITLE.fullmatch(title)
                    or _PENDING_TITLE.fullmatch(title))
        return (recovery is not None and recovery.group(1) == task
                and (attempt is None or attempt == 1)
                and (sha is None or recovery.group(2) == sha))
    if event == "workflow_run":
        match = _AUTO_TITLE.fullmatch(title)
        return (match is not None and match.group(1) == task and
                (sha is None or match.group(2) == sha) and
                (branch is None or branch == "lf/native-proposal/" + task))
    return False


def _collect_prior(repository, token, task, run_id, sha, results, *,
                   event=None, attempt=None, route_retry=False, current=(), strict=False):
    # Only a trusted, merged launcher-only migration may forgive a previously
    # spent proof. The immutable source run and original pack must still match.
    from native_route_defect import verified_migration
    control = Path(__file__).resolve().parents[2]
    registration = storage_path("registrations_root", root=control) / (task + ".json")
    try:
        record = json.loads(registration.read_text("utf-8"))
    except (OSError, ValueError):
        record = {}
    migration = verified_migration(control, task, record)
    # T32: governed examiner-defect forgiveness (exact runs, replaced exam).
    from native_examiner_defect import verified_examiner_defects
    examiner_defects = verified_examiner_defects(control, task, record)
    # T37: governed route-tool-defect forgiveness (exact runs, fixed tool, re-pinned base).
    from native_route_tool_defect import verified_route_tool_defects
    for forgiven_id, row in verified_route_tool_defects(control, task, record).items():
        examiner_defects.setdefault(forgiven_id, row)
    # T38: governed forgiveness of pre-T38 runs whose patch could not apply.
    from native_intake_defect import verified_intake_defects
    for forgiven_id, row in verified_intake_defects(control, task, record).items():
        examiner_defects.setdefault(forgiven_id, row)
    if route_retry and (
        event != "workflow_dispatch" or attempt != 1
        or migration is None or migration["proposal_commit_sha"] != sha
        or _ROUTE_TITLE.fullmatch(current[0].get("display_title") or "") is None
    ):
        raise ValueError("NATIVE_ROUTE_RETRY_NOT_ATTESTED")
    if strict:
        # No further forgiveness may renew this one-use successor budget.
        migration, examiner_defects = None, {}
    prior: list[dict] = []
    route_defect_run_ids: list[int] = []
    for run in results:
        if run.get("id") == run_id:
            continue
        # The run title/branch must match the requested task BEFORE download.
        if not _recognized_run(run, task):
            continue
        # A missing OR expired proof is grandfathered only before the
        # immutable PR #370 merge, except for explicitly blocked run IDs.
        # Post-cutover proof absence always requires authentic NO_ATTEMPT
        # evidence or a provably unstarted Worker job.
        try:
            proof = _artifact_json(repository, token, run["id"])
        except ValueError as exc:
            if str(exc) != "NATIVE_PRIOR_PROOF_MISSING":
                raise
            if strict or not _r3_pre_cutover(repository, token, run):
                raise
            continue  # pre-merge expired proof: legacy never counted
        if proof is None:
            if run.get("status") != "completed":
                if strict and run.get("status") == "in_progress":
                    raise ValueError("LOT_RECOVERY_CONCURRENT_RUN")
                continue
            if _no_attempt_attested(repository, token, run, task):
                continue
            if not strict and _r3_pre_cutover(repository, token, run):
                continue  # pre-merge missing proof, legacy non-attempt
            raise ValueError("NATIVE_PRIOR_PROOF_MISSING")
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
        if (migration is not None and run["id"] == migration["source_run_id"]
                and run.get("status") == "completed"
                and run.get("conclusion") == "failure"
                and proof["task_pack_sha256"] == migration["legacy_task_pack_sha256"]
                and _recognized_run(run, task, sha=migration["proposal_commit_sha"])):
            # The route-owned interpreter failure is retained in GitHub
            # history but does not consume a constructor attempt.
            route_defect_run_ids.append(run["id"])
            continue
        forgiven = examiner_defects.get(run["id"])
        if (forgiven is not None and run.get("status") == "completed"
                and run.get("conclusion") == "failure"
                and proof["task_pack_sha256"] == forgiven["task_pack_sha256"]
                and _recognized_run(run, task, sha=forgiven["proposal_commit_sha"])):
            route_defect_run_ids.append(run["id"])
            continue
        title = run.get("display_title") or ""
        match = (_AUTO_TITLE.fullmatch(title)
                 if run.get("event") == "workflow_run"
                 else (_INFRA_TITLE.fullmatch(title) or
                       _ROUTE_TITLE.fullmatch(title) or
                       _PENDING_TITLE.fullmatch(title)))
        manual = (_MANUAL_TITLE.fullmatch(title)
                  if run.get("event") == "workflow_dispatch" else None)
        prior_sha = (match.group(2) if match is not None else
                     manual.group(4) if manual is not None else None)
        if sha is not None and prior_sha == sha:
            raise ValueError("NATIVE_DUPLICATE_PROPOSAL_SHA")
        prior.append(proof)
    return prior, route_defect_run_ids


def admit_attempt(
    *, repository: str, token: str, task: str, attempt: int | None,
    run_id: int, run_attempt: int, sha: str, output: Path,
    event: str = "workflow_dispatch", head_branch: str = "main",
    proposal_branch: str | None = None, github_output: Path | None = None,
    route_retry: bool = False,
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
                            sha=sha,
                            branch=proposal_branch,
                            allow_legacy_manual=False)):
        raise ValueError("NATIVE_CURRENT_RUN_NOT_ATTESTED")
    from pilot.orchestrator.lot_recovery import for_successor, verify_original, require_unused
    control = Path(__file__).resolve().parents[2]
    recovery = for_successor(control, task)
    if recovery:
        if route_retry:
            raise ValueError("LOT_RECOVERY_ROUTE_RETRY_FORBIDDEN")
        original, forgiven = _collect_prior(
            repository, token, recovery["original_task"], run_id, None, results)
        verify_original(recovery, original, forgiven, results)
    prior, route_defect_run_ids = _collect_prior(
        repository, token, task, run_id, sha, results, event=event,
        attempt=attempt, route_retry=route_retry, current=current, strict=bool(recovery))
    if recovery:
        require_unused(prior)
    computed = len(prior) + 1
    if computed > 3:
        raise ValueError("NATIVE_ATTEMPT_LIMIT_EXCEEDED")
    if attempt is not None and attempt != computed:
        raise ValueError("NATIVE_ATTEMPT_COUNT_MISMATCH")
    prior.sort(key=lambda entry: entry["attempt"])
    validate_attempt_history(task, computed, prior)
    result = {"prior_run_ids": [x["run_id"] for x in prior],
              "route_defect_run_ids": sorted(route_defect_run_ids),
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
    parser.add_argument("--route-retry", action="store_true")
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
                  route_retry=a.route_retry,
                  github_output=a.github_output)


if __name__ == "__main__":
    main()
