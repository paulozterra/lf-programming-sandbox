"""Independent format budget backed exclusively by trusted Actions evidence.

No functional proof, forgiveness or counter is changed. Missing evidence after
activation is a hard stop. The merge timestamp of this PR is the historical
boundary; an unmerged or unresolved boundary cannot authorize a live run.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from native_format_admission import (
    ROOT, SHA40, CONTINUE, BLOCK, FormatResult, _public, identity, checkout_identity,
)
from native_proposal_client import read_proposal_envelope
from native_run_history import _recognized_run, _api
from native_feedback_delivery import (
    REPO, issue_for_task, request_state, OPEN, _subprocess, PRIVATE,
)
from programming_agent_runner.worker_secrets import secret_text_reason

BUDGET_GATE = "Admit independent format rejection budget"
GATE = "Prevalidate native proposal format before examiner material"
UPLOAD = "Upload public native format preflight evidence"
WORKER = "Execute original run_verified_worker using native proposal (single attempt)"
ARTIFACT = "native-format-preflight"
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
FIELDS = {"schema_version", "task_id", "proposal_commit_sha", "run_id",
          "next_functional_attempt", "functional_attempt_consumed",
          "task_pack_sha256", "proposal_sha256", "patch_sha256",
          "status", "reason", "paths", "diagnostics"}
HASHES = ("task_pack_sha256", "proposal_sha256", "patch_sha256")
LIMIT = 3


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def stamp(value):
    require(isinstance(value, str), "FORMAT_HISTORY_DATE_INVALID")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(parsed.tzinfo is not None, "FORMAT_HISTORY_DATE_INVALID")
    return parsed.astimezone(timezone.utc)


def cutover(api):
    # Follow-up owner/Train pin, once actual merge metadata exists.
    pin = Path(__file__).with_name("format_cutover.json")
    require(not pin.is_symlink(), "FORMAT_CUTOVER_UNRESOLVED")
    if pin.exists():
        pr = json.loads(pin.read_text("utf-8"))
        require(set(pr) == {"schema_version", "pr_number", "merge_commit_sha", "merged_at"}
                and pr["schema_version"] == "LF_FORMAT_CUTOVER_V1" and pr["pr_number"] == 816
                and SHA40.fullmatch(pr["merge_commit_sha"] or "") is not None,
                "FORMAT_CUTOVER_UNRESOLVED")
        return stamp(pr["merged_at"])
    pr = api("pulls/816")
    require(pr.get("number") == 816 and pr.get("merged") is True
            and SHA40.fullmatch(pr.get("merge_commit_sha") or "") is not None
            and pr.get("base", {}).get("ref") == "main",
            "FORMAT_CUTOVER_UNRESOLVED")
    return stamp(pr.get("merged_at"))


def listed(api):
    rows = []
    total = None
    for page in range(1, 11):
        obj = api(f"actions/workflows/worker-native.yml/runs?per_page=100&page={page}")
        n, batch = obj.get("total_count"), obj.get("workflow_runs")
        require(type(n) is int and 0 <= n <= 1000 and isinstance(batch, list),
                "FORMAT_HISTORY_INCOMPLETE")
        if total is None:
            total = n
        require(n == total, "FORMAT_HISTORY_CHANGED")
        rows.extend(batch)
        if len(rows) >= total:
            break
    require(len(rows) == total and all(type(x.get("id")) is int for x in rows)
            and len({x["id"] for x in rows}) == len(rows), "FORMAT_HISTORY_INCOMPLETE")
    return rows


def proposal_sha(run, task):
    title = run.get("display_title") or ""
    sha = title.rsplit("-", 1)[-1]
    require(SHA40.fullmatch(sha) is not None and
            _recognized_run(run, task, sha=sha, allow_legacy_manual=False),
            "FORMAT_RUN_IDENTITY_INVALID")
    return sha


def trusted_run(run, repo):
    require(run.get("head_branch") == "main" and run.get("run_attempt") == 1
            and (run.get("repository") or {}).get("full_name") == repo
            and (run.get("path") or "").split("@")[0] == ".github/workflows/worker-native.yml",
            "FORMAT_RUN_UNTRUSTED")


def steps(api, run):
    obj = api(f"actions/runs/{run['id']}/jobs?per_page=100")
    jobs = obj.get("jobs")
    require(isinstance(jobs, list) and obj.get("total_count") == len(jobs),
            "FORMAT_JOB_HISTORY_INCOMPLETE")
    if not jobs and run.get("conclusion") in ("cancelled", "skipped"):
        return None
    require(len(jobs) == 1 and jobs[0].get("name") == "native",
            "FORMAT_JOB_HISTORY_INVALID")
    if jobs[0].get("conclusion") == "skipped":
        return None
    rows = jobs[0].get("steps")
    require(isinstance(rows, list), "FORMAT_STEP_HISTORY_INVALID")
    relevant = [s for s in rows if s.get("name") in (BUDGET_GATE, GATE, UPLOAD, WORKER)]
    names = [s.get("name") for s in relevant]
    require(len(names) == len(set(names)), "FORMAT_STEP_HISTORY_DUPLICATE")
    return {s["name"]: s.get("conclusion") for s in relevant}


def envelope_at(api, task, sha):
    # Immutable historical commit, never branch HEAD. Revalidate canonical
    # envelope with the same reader used by the Worker.
    value = api(f"contents/pilot/native_proposals/{task}.json?ref={sha}")
    require(value.get("type") == "file" and value.get("encoding") == "base64"
            and type(value.get("size")) is int and 0 < value["size"] <= 1_000_000,
            "FORMAT_HISTORICAL_ENVELOPE_INVALID")
    raw = base64.b64decode("".join(value["content"].splitlines()), validate=True)
    require(len(raw) == value["size"], "FORMAT_HISTORICAL_ENVELOPE_INVALID")
    with tempfile.TemporaryDirectory() as directory:
        file = Path(directory) / "proposal.json"
        file.write_bytes(raw)
        return read_proposal_envelope(file)


def download(api, command, repo, run_id):
    obj = api(f"actions/runs/{run_id}/artifacts?per_page=100")
    rows = obj.get("artifacts")
    require(isinstance(rows, list) and obj.get("total_count") == len(rows),
            "FORMAT_ARTIFACT_INVENTORY_INCOMPLETE")
    found = [x for x in rows if x.get("name") == ARTIFACT]
    require(len(found) == 1, "FORMAT_EVIDENCE_MISSING_OR_DUPLICATE")
    item = found[0]
    require(item.get("expired") is False and item.get("workflow_run", {}).get("id") == run_id
            and type(item.get("size_in_bytes")) is int and 0 < item["size_in_bytes"] <= 100_000,
            "FORMAT_EVIDENCE_EXPIRED_OR_UNTRUSTED")
    with tempfile.TemporaryDirectory(prefix="lf-format-evidence-") as directory:
        command("gh", "run", "download", str(run_id), "--repo", repo,
                "--name", ARTIFACT, "--dir", directory)
        folder = Path(directory)
        file = folder / "format-result.json"
        require(list(folder.iterdir()) == [file] and file.is_file()
                and not file.is_symlink() and file.stat().st_size <= 64_000,
                "FORMAT_EVIDENCE_FILE_INVALID")
        return json.loads(file.read_text("utf-8"))


def validate(data, task, run_id, sha, outcome, envelope=None):
    require(isinstance(data, dict) and set(data) == FIELDS
            and data["schema_version"] == "LF_NATIVE_FORMAT_RESULT_V2"
            and data["task_id"] == task and type(data["run_id"]) is int and data["run_id"] == run_id
            and data["proposal_commit_sha"] == sha
            and type(data["next_functional_attempt"]) is int and 1 <= data["next_functional_attempt"] <= 3
            and data["functional_attempt_consumed"] is False
            and data["status"] in CONTINUE | BLOCK
            and (data["status"] in CONTINUE) == (outcome == "success")
            and isinstance(data["paths"], list) and isinstance(data["diagnostics"], list)
            and all(isinstance(x, str) for x in data["paths"] + data["diagnostics"]),
            "FORMAT_EVIDENCE_IDENTITY_MISMATCH")
    public = {k: data[k] for k in ("status", "reason", "paths", "diagnostics")}
    require(public == _public(FormatResult(data["status"], data["reason"],
                    paths=tuple(data["paths"]), diagnostics=tuple(data["diagnostics"]))),
            "FORMAT_EVIDENCE_UNSAFE")
    require(not PRIVATE.search(json.dumps(public)) and not secret_text_reason(json.dumps(public)),
            "FORMAT_EVIDENCE_UNSAFE")
    hashes = {k: data[k] for k in HASHES}
    if data["status"] == "FORMAT_FAIL":
        require(data["reason"] == "SPOTLESS_VIOLATIONS" and envelope is not None
                and all(isinstance(v, str) and SHA64.fullmatch(v) for v in hashes.values())
                and hashes == identity(envelope)
                and set(data["paths"]).issubset(envelope["proposal"]["changed_paths"]),
                "FORMAT_EVIDENCE_HASH_MISMATCH")
    else:
        require((envelope is not None and all(isinstance(v, str) and SHA64.fullmatch(v) for v in hashes.values())
                 and hashes == identity(envelope))
                or (all(v is None for v in hashes.values()) and data["status"] in
                    ("INVALID_PROPOSAL", "INFRA_ERROR")), "FORMAT_EVIDENCE_HASH_INVALID")
    return data


def result_for_run(api, command, repo, row, task):
    """Classify a completed post-cutover run, including cancelled runs.

    A completed failed gate without a published result is ambiguous even
    when the overall run was cancelled. Never silently waive that evidence.
    """
    trusted_run(row, repo)
    require(row.get("status") == "completed", "FORMAT_RUN_UNRESOLVED")
    observed = steps(api, row)
    def absent_on_cancel():
        inventory = api(f"actions/runs/{row['id']}/artifacts?per_page=100")
        items = inventory.get("artifacts")
        require(isinstance(items, list) and inventory.get("total_count") == len(items)
                and not any(x.get("name") in (ARTIFACT, "native-attempt-proof") for x in items),
                "FORMAT_CANCEL_EVIDENCE_CONTRADICTORY")
    if observed is None:
        if row.get("conclusion") == "cancelled":
            absent_on_cancel()
        return None
    require(GATE in observed, "FORMAT_GATE_HISTORY_MISSING")
    outcome = observed[GATE]
    upload = observed.get(UPLOAD)
    if outcome in ("skipped", "cancelled"):
        require(upload in (None, "skipped", "cancelled"), "FORMAT_CANCEL_EVIDENCE_CONTRADICTORY")
        require(observed.get(WORKER) in (None, "skipped", "cancelled"),
                "FORMAT_CANCEL_EVIDENCE_CONTRADICTORY")
        if row.get("conclusion") == "cancelled":
            absent_on_cancel()
        return None
    require(outcome in ("success", "failure") and upload == "success",
            "FORMAT_EVIDENCE_NOT_ATTESTED")
    sha = proposal_sha(row, task)
    data = download(api, command, repo, row["id"])
    require(isinstance(data, dict), "FORMAT_EVIDENCE_FILE_INVALID")
    envelope = envelope_at(api, task, sha) if any(data.get(k) is not None for k in HASHES) else None
    validate(data, task, row["id"], sha, outcome, envelope)
    if data["status"] in BLOCK:
        require(row.get("conclusion") in ("failure", "cancelled")
                and observed.get(WORKER) in ("skipped", None)
                and (observed.get(WORKER) == "skipped" or row.get("conclusion") == "cancelled"),
                "FORMAT_WORKER_NOT_SKIPPED")
    return data


def historical_rejections(api, command, repo, task, run_id, sha):
    boundary = cutover(api)
    rows = listed(api)
    current = [r for r in rows if r["id"] == run_id]
    require(len(current) == 1, "FORMAT_CURRENT_RUN_MISSING")
    trusted_run(current[0], repo)
    require(proposal_sha(current[0], task) == sha and stamp(current[0].get("created_at")) >= boundary,
            "FORMAT_CURRENT_RUN_MISMATCH")
    rejected = {}
    for row in sorted(rows, key=lambda r: r["id"]):
        if row["id"] == run_id or not _recognized_run({**row, "run_attempt": 1}, task):
            continue
        if stamp(row.get("created_at")) < boundary:
            continue
        # Re-running a GitHub run changes its attempt metadata. Never silently
        # drop an earlier format rejection because somebody re-ran its job.
        trusted_run(row, repo)
        if row["id"] > run_id and row.get("status") != "completed":
            continue  # newer queued runs have not executed under task concurrency
        require(row["id"] < run_id and row.get("status") == "completed",
                "FORMAT_HISTORY_CONCURRENT_OR_UNRESOLVED")
        data = result_for_run(api, command, repo, row, task)
        if data is not None and data["status"] == "FORMAT_FAIL":
            rejected.setdefault(data["patch_sha256"], data)
    return rejected


def budget(rejected, hashes):
    if len(rejected) >= LIMIT:
        return "FORMAT_REJECTION_LIMIT_EXCEEDED"
    if hashes and hashes["patch_sha256"] in rejected:
        return "FORMAT_DUPLICATE_REJECTED_PATCH"
    return "FORMAT_BUDGET_AVAILABLE"


def publish(command, api, repo, control, task, data):
    # Only the separate write-capable trusted step calls this function.
    number = issue_for_task(control, task)
    if request_state("req-" + str(number), api, root=control) != OPEN:
        return "FORMAT_REQUEST_CLOSED"
    issue = api(f"issues/{number}")
    require(issue.get("number") == number and not issue.get("pull_request")
            and issue.get("state") == "open", "FORMAT_ISSUE_INVALID")
    status = data["status"]
    require(status in ("FORMAT_FAIL", "INVALID_PROPOSAL", "BASELINE_FAIL"), "FORMAT_FEEDBACK_STATUS_INVALID")
    key = (f"<!-- LF_NATIVE_FORMAT_FEEDBACK:{task}:{data['patch_sha256']} -->" if status == "FORMAT_FAIL"
           else f"<!-- LF_NATIVE_FORMAT_NOTICE:{task}:{data['proposal_commit_sha']}:{status} -->")
    for page in range(1, 11):
        comments = json.loads(command("gh", "api", f"repos/{repo}/issues/{number}/comments?per_page=100&page={page}"))
        require(isinstance(comments, list), "FORMAT_FEEDBACK_HISTORY_INVALID")
        if any(key in str(c.get("body") or "") and (c.get("user") or {}).get("login") == "github-actions[bot]" for c in comments):
            return "FORMAT_FEEDBACK_ALREADY_PUBLISHED"
        if len(comments) < 100:
            break
    else:
        raise ValueError("FORMAT_FEEDBACK_HISTORY_INCOMPLETE")
    body = (key + "\nPrevalidación Spotless: " + status + " (sin intento funcional).\n"
            + "Tarea: " + task + "\nPropuesta: " + data["proposal_commit_sha"]
            + "\nRun: " + str(data["run_id"]) + "\nMotivo: " + data["reason"] + "\n"
            + "\n".join(data["diagnostics"])
            + ("\nCorrige el formato y presenta un parche diferente." if status == "FORMAT_FAIL"
               else "\nRevisa la propuesta registrada." if status == "INVALID_PROPOSAL"
               else "\nDefecto de base: requiere revisión del owner; no imputable al constructor."))
    command("gh", "issue", "comment", str(number), "--repo", repo, "--body", body)
    return "FORMAT_FEEDBACK_PUBLISHED"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("budget", "publish"))
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--run-id", type=int, required=True)
    a = parser.parse_args()
    repo, token = os.environ["GITHUB_REPOSITORY"], os.environ["GH_TOKEN"]
    require(repo == REPO and token and a.run_id == int(os.environ["GITHUB_RUN_ID"]),
            "FORMAT_HISTORY_CONTEXT_INVALID")
    api = lambda route: _api(repo, token, route)
    if a.mode == "budget":
        prior = historical_rejections(api, _subprocess, repo, a.task, a.run_id, a.sha)
        try:
            hashes = checkout_identity(a.proposal, a.task)
        except Exception:
            hashes = None  # isolated admission owns invalid proposal classification
        result = budget(prior, hashes)
        print(result)
        if result != "FORMAT_BUDGET_AVAILABLE":
            raise SystemExit(1)
    else:
        run = api(f"actions/runs/{a.run_id}")
        trusted_run(run, repo)
        require(proposal_sha(run, a.task) == a.sha, "FORMAT_CURRENT_RUN_MISMATCH")
        data = download(api, _subprocess, repo, a.run_id)
        observed = steps(api, run)
        require(observed.get(GATE) == "failure" and observed.get(UPLOAD) == "success",
                "FORMAT_EVIDENCE_NOT_ATTESTED")
        envelope = envelope_at(api, a.task, a.sha) if any(data.get(k) is not None for k in HASHES) else None
        validate(data, a.task, a.run_id, a.sha, "failure", envelope)
        if data["status"] in ("FORMAT_FAIL", "INVALID_PROPOSAL", "BASELINE_FAIL"):
            print(publish(_subprocess, api, repo, a.control, a.task, data))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Never expose arbitrary API or proposal content.
        code = str(exc)
        print(code if re.fullmatch(r"FORMAT_[A-Z0-9_]+", code) else "FORMAT_HISTORY_UNAVAILABLE")
        raise SystemExit(1)
