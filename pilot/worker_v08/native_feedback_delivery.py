"""T22: publish only schema-verified visible native feedback to its LF request issue.

Trusted main code only. Never read or publish an oracle, private evidence, or
hidden acceptance result. The GitHub issue comment marker is the durable ledger.
"""
from __future__ import annotations
# Resolve the trusted repository package for direct script execution.
import sys as _project_sys
from pathlib import Path as _project_Path
_project_sys.path.insert(0, str(_project_Path(__file__).resolve().parents[2]))
from pilot.config.project_config import storage_path, storage

import argparse
import json
import os
from pathlib import Path
from pilot.orchestrator.request_lifecycle import request_state, OPEN, RequestStateError, inactive_reason
import re
import subprocess
import tempfile

REPO = "paulozterra/lf-programming-sandbox"
SCHEMA = "LF_NATIVE_VISIBLE_FEEDBACK_V1"
CMD_KEYS = frozenset({"name", "status", "reason", "returncode",
                       "stdout_excerpt", "stderr_excerpt"})
TOP_KEYS = frozenset({"schema_version", "attempt", "kind", "commands"})
TASK = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
SHA = re.compile(r"[0-9a-f]{40}\Z")
REQUEST = re.compile(r"req-[1-9][0-9]*\Z")
AUTO = re.compile(r"lf-native-auto-lf/native-proposal/([a-z][a-z0-9_-]{0,31})-([0-9a-f]{40})\Z")
MANUAL = re.compile(r"lf-native-([a-z][a-z0-9_-]{0,31})-a[123]-([0-9a-f]{40})\Z")
ROUTE_REPLAY = re.compile(r"lf-native-route-retry-([a-z][a-z0-9_-]{0,31})-([0-9a-f]{40})\Z")
INFRA = re.compile(r"lf-native-infra-retry-([a-z][a-z0-9_-]{0,31})-([0-9a-f]{40})\Z")
# T28.1: block exam material and real secret VALUES, not ordinary words.
# Visible build/test output of an auth feature legitimately says "token",
# "secret" or "private"; blocking those words hid all feedback from the
# constructor. Exam references and concrete credential values stay blocked.
PRIVATE = re.compile(
    r"oracle|holdout|"
    r"comando[s]? oculto[s]?|examen oculto|/native-private/|"
    r"pil[o]t/holdouts/|holdout_sha256|"
    r"\$2[aby]\$[0-9]{2}\$[./A-Za-z0-9]{20,}|"          # bcrypt hash value
    r"bearer\s+[A-Za-z0-9._~+/=-]{16,}|"                  # concrete bearer token
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|AGE-SECRET-KEY-",  # key material
    re.IGNORECASE,
)
MAX = 100
MAX_BYTES = 24_000
# T28.2: the Worker keeps up to 4000 characters of each command's output
# (vendor worker.py). Accept exactly that excerpt (<= 4 bytes per char);
# a stricter limit silently withheld real visible feedback (e.g. Spotless).
FIELD_MAX_BYTES = 16_000
WORKSPACE_PREFIX = re.compile(r"(?:/[^\s\"'/]+)*/native-private/(?:workspace[^\s\"'/]*/)?")


class FeedbackBlocked(ValueError):
    pass


def deny(reason: str = "") -> None:
    # T28.3: name the failed rule (never the content) so a withheld feedback
    # can be diagnosed from the sweep outcome.
    raise FeedbackBlocked("FEEDBACK_NO_PUBLICO" + (":" + reason if reason else ""))


def parse_feedback(raw: bytes, attempt: int) -> dict:
    if type(attempt) is not int or not 1 <= attempt <= 3:
        deny("ATTEMPT")
    if len(raw) > MAX_BYTES:
        deny("TOTAL_SIZE")
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeError):
        deny("JSON")
    if (not isinstance(data, dict) or set(data) != TOP_KEYS
            or data.get("schema_version") != SCHEMA
            or data.get("kind") != "VISIBLE_ACCEPTANCE_ONLY"
            or data.get("attempt") != attempt
            or not isinstance(data.get("commands"), list)
            or len(data["commands"]) > 30):
        deny("SCHEMA_TOP" + (":ATTEMPT_MISMATCH" if isinstance(data, dict)
                             and data.get("attempt") != attempt else ""))
    for command in data["commands"]:
        if not isinstance(command, dict) or set(command) != CMD_KEYS:
            deny("SCHEMA_COMMAND")
        for name, value in command.items():
            if name == "returncode":
                if value is not None and (type(value) is not int or abs(value) > 32768):
                    deny("RETURNCODE")
            elif value is not None and (not isinstance(value, str)
                                        or len(value.encode("utf-8")) > FIELD_MAX_BYTES):
                deny("FIELD_SIZE")
    # T28.4: the Worker runs commands inside its workspace under the private
    # runner directory, so tool output (Maven, Spotless) carries that absolute
    # path. Replace only the path prefix with a neutral marker; any exam file
    # name after it (oracle, holdout) is still caught below.
    for command in data["commands"]:
        for name in ("stdout_excerpt", "stderr_excerpt", "reason"):
            if isinstance(command.get(name), str):
                command[name] = WORKSPACE_PREFIX.sub("<worker-workspace>/", command[name])
    # Same public object otherwise. Check the *entire* serialized payload.
    serialized = json.dumps(data, sort_keys=True, ensure_ascii=False)
    if PRIVATE.search(serialized):
        deny("PRIVATE_PATTERN")
    return data


def marker(task: str, sha: str, attempt: int) -> str:
    if not TASK.fullmatch(task) or not SHA.fullmatch(sha) or not 1 <= attempt <= 3:
        deny("MARKER_1")
    return f"<!-- LF_NATIVE_VISIBLE_FEEDBACK:{task}:{sha}:{attempt} -->"


def issue_for_task(root: Path, task: str) -> int:
    if not TASK.fullmatch(task):
        deny("ISSUE_FOR_TASK_1")
    registered = storage_path("registrations_root", root=root) / (task + ".json")
    if registered.is_symlink() or not registered.is_file():
        deny("ISSUE_FOR_TASK_2")
    matches = []
    for file in sorted((storage_path("requests_root", root=root)).glob(
            "req-*/proposal_requests/" + task + ".proposal-request.json")):
        folder = file.parent.parent
        if (file.is_symlink() or folder.is_symlink()
                or not REQUEST.fullmatch(folder.name)):
            deny("ISSUE_FOR_TASK_3")
        request = folder.name
        meta = folder / "request_meta.json"
        if meta.is_symlink() or not meta.is_file():
            deny("ISSUE_FOR_TASK_4")
        try:
            envelope = json.loads(file.read_text("utf-8"))
            metadata = json.loads(meta.read_text("utf-8"))
        except (ValueError, UnicodeError, OSError):
            deny("ISSUE_FOR_TASK_5")
        if (not isinstance(envelope, dict)
                or envelope.get("branch") != "lf/native-proposal/" + task
                or not isinstance(metadata, dict)
                or metadata.get("issue") != int(request[4:])):
            deny("ISSUE_FOR_TASK_6")
        matches.append(int(request[4:]))
    if len(matches) != 1:
        deny("ISSUE_FOR_TASK_7")
    return matches[0]


def read_public(path: Path, attempt: int) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        deny("READ_PUBLIC_1")
    return parse_feedback(path.read_bytes(), attempt)


def publish(run, api, repo: str, root: Path, task: str, sha: str,
            attempt: int, feedback: dict, result: str,
            *, route_replay_run_id: int | None = None) -> str:
    key = marker(task, sha, attempt)
    if route_replay_run_id is not None:
        if type(route_replay_run_id) is not int or route_replay_run_id <= 0:
            deny("PUBLISH_1")
        key = (f"<!-- LF_NATIVE_ROUTE_REPLAY_FEEDBACK:{task}:{sha}:"
               f"{attempt}:{route_replay_run_id} -->")
    if result not in ("PASS", "FAIL", "BLOCKED_OR_FAILED"):
        deny("PUBLISH_2")
    # Validate again at the publishing boundary; no bypass from a caller.
    payload = json.dumps(feedback, sort_keys=True, ensure_ascii=False).encode("utf-8")
    feedback = parse_feedback(payload, attempt)
    number = issue_for_task(root, task)
    try:
        state = request_state("req-" + str(number), api, root=root)
    except RequestStateError as exc:
        raise FeedbackBlocked("REQUEST_STATE_UNRESOLVED") from exc
    if state != OPEN:
        return inactive_reason(state)
    issue = api(f"issues/{number}")
    # T35: the request identity is proven by issue_for_task (registered task
    # + trusted pilot/runs/req-N/request_meta.json on main). The lf-request
    # label is only added by the web form; Issues created through the API
    # (e.g. the GPT connector) do not carry it, so it is not required here.
    if (issue.get("number") != number or issue.get("pull_request")
            or issue.get("state") != "open"):
        deny("PUBLISH_3")
    raw_comments = run("gh", "api", f"repos/{repo}/issues/{number}/comments?per_page=100")
    try:
        comments = json.loads(raw_comments)
    except ValueError:
        deny("PUBLISH_4")
    if not isinstance(comments, list) or len(comments) >= MAX:
        deny("PUBLISH_5")
    if any(key in str(c.get("body") or "")
           for c in comments if isinstance(c, dict)
           and (c.get("user") or {}).get("login") == "github-actions[bot]"):
        return "FEEDBACK_ALREADY_PUBLISHED"
    body = (key + "\nFeedback visible del Worker nativo (sin examen oculto).\n\n"
            + "**Tarea:** `" + task + "`\n"
            + "**Intento:** " + str(attempt) + "/3\n"
            + "**SHA de propuesta:** `" + sha + "`\n"
            + "**Resultado:** " + result + "\n"
            + "**Feedback visible (public/feedback.json):**\n"
            + "```json\n" + json.dumps(feedback, ensure_ascii=False,
                                             sort_keys=True, indent=2)
            + "\n```")
    try:
        state = request_state("req-" + str(number), api, root=root)
    except RequestStateError as exc:
        raise FeedbackBlocked("REQUEST_STATE_UNRESOLVED") from exc
    if state != OPEN:
        return inactive_reason(state)
    run("gh", "issue", "comment", str(number), "--repo", repo, "--body", body)
    return "FEEDBACK_PUBLISHED"


def _artifact_names(api, run_id: int) -> bool:
    obj = api(f"actions/runs/{run_id}/artifacts?per_page=100")
    artifacts = obj.get("artifacts")
    if (not isinstance(artifacts, list) or type(obj.get("total_count")) is not int
            or obj["total_count"] > MAX or len(artifacts) >= MAX):
        deny("ARTIFACT_NAMES_1")
    for name in ("native-attempt-proof", "native-visible-feedback-and-cost"):
        found = [a for a in artifacts if isinstance(a, dict) and a.get("name") == name]
        if (len(found) != 1 or found[0].get("expired") is True
                or found[0].get("workflow_run", {}).get("id", run_id) != run_id):
            return False
    return True


def _run_identity(item: dict, repo: str):
    if (not isinstance(item, dict) or type(item.get("id")) is not int
            or item.get("event") not in ("workflow_dispatch", "workflow_run")
            or item.get("head_branch") != "main"
            or item.get("status") != "completed"
            or item.get("conclusion") not in ("success", "failure")
            or item.get("run_attempt") != 1
            or (item.get("path") or "").split("@")[0] != ".github/workflows/worker-native.yml"
            or (item.get("repository") or {}).get("full_name") != repo):
        return None
    title = item.get("display_title") or ""
    match = ((INFRA.fullmatch(title) or ROUTE_REPLAY.fullmatch(title) or MANUAL.fullmatch(title))
             if item["event"] == "workflow_dispatch"
             else AUTO.fullmatch(title))
    return (match.group(1), match.group(2)) if match else None


def recover_one(run, api, repo: str, root: Path, item: dict) -> str:
    identity = _run_identity(item, repo)
    if identity is None:
        return "FEEDBACK_RUN_NOT_ELIGIBLE"
    task, sha = identity
    # Legacy synthetic Workers have no issue-backed request; skip those runs.
    # An unmapped task is not an unsafe feedback payload.
    try:
        issue_for_task(root, task)
    except FeedbackBlocked:
        return "FEEDBACK_NO_SOURCE_ISSUE"
    run_id = item["id"]
    jobs = api(f"actions/runs/{run_id}/jobs?per_page=100")
    jobrows = jobs.get("jobs")
    if (not isinstance(jobrows, list) or len(jobrows) != 1
            or jobs.get("total_count") != 1
            or jobrows[0].get("name") != "native"):
        deny("RECOVER_ONE_1")
    steps = jobrows[0].get("steps")
    if (not isinstance(steps, list)
            or not any(s.get("name") == "Execute original run_verified_worker using native proposal (single attempt)"
                       and s.get("conclusion") in ("success", "failure")
                       for s in steps if isinstance(s, dict))):
        return "FEEDBACK_NO_SPENT_ATTEMPT"
    if not _artifact_names(api, run_id):
        return "FEEDBACK_ARTIFACT_MISSING"
    with tempfile.TemporaryDirectory(prefix="lf-t22-") as directory:
        folder = Path(directory)
        for name in ("native-attempt-proof", "native-visible-feedback-and-cost"):
            location = folder / name
            location.mkdir()
            run("gh", "run", "download", str(run_id), "--repo", repo,
                "--name", name, "--dir", str(location))
        proof_file = folder / "native-attempt-proof/attempt-proof.json"
        if proof_file.is_symlink() or not proof_file.is_file() or proof_file.stat().st_size > 4096:
            deny("RECOVER_ONE_2")
        try:
            proof = json.loads(proof_file.read_text("utf-8"))
        except (ValueError, UnicodeError):
            deny("RECOVER_ONE_3")
        if (not isinstance(proof, dict)
                or set(proof) != {"task_id", "attempt", "task_pack_sha256", "run_id"}
                or proof.get("task_id") != task or proof.get("run_id") != run_id
                or type(proof.get("attempt")) is not int
                or not 1 <= proof["attempt"] <= 3):
            deny("RECOVER_ONE_4")
        file = folder / "native-visible-feedback-and-cost/feedback.json"
        feedback = read_public(file, proof["attempt"])
        result = ("PASS" if item["conclusion"] == "success"
                  else "BLOCKED_OR_FAILED")
        return publish(run, api, repo, root, task, sha, proof["attempt"],
                       feedback, result,
                       route_replay_run_id=(run_id if ROUTE_REPLAY.fullmatch(
                           item.get("display_title") or "") else None))


def recover_sweep(run, api, repo: str, root: Path) -> list[dict]:
    response = api("actions/workflows/worker-native.yml/runs?per_page=100")
    rows = response.get("workflow_runs")
    if (not isinstance(rows, list) or type(response.get("total_count")) is not int
            or len(rows) > MAX):
        return [{"status": "FEEDBACK_HISTORY_INCOMPLETE"}]
    result = []
    for item in rows:
        if _run_identity(item, repo) is None:
            continue
        try:
            status = recover_one(run, api, repo, root, item)
            result.append({"status": status, "run_id": item["id"]})
        except FeedbackBlocked as exc:
            result.append({"status": "FEEDBACK_NO_PUBLICO", "run_id": item["id"]})
            # Do not publish anything from an unsafe artifact. Name the run and
            # the failed rule (T28.3), never the content.
            raise FeedbackBlocked(f"{exc}:RUN_{int(item['id'])}") from None
    return result


def _subprocess(*args: str) -> str:
    result = subprocess.run(args, text=True, capture_output=True, timeout=90)
    if result.returncode:
        raise FeedbackBlocked("FEEDBACK_GITHUB_UNAVAILABLE")
    return result.stdout.strip()


def _api(repo: str, route: str) -> dict:
    try:
        value = json.loads(_subprocess("gh", "api", f"repos/{repo}/{route}"))
    except ValueError:
        deny("API_1")
    if not isinstance(value, dict):
        deny("API_2")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--attempt", type=int, required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--feedback", type=Path, required=True)
    parser.add_argument("--outcome", choices=["success", "failure"], required=True)
    args = parser.parse_args()
    if (not os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_REPOSITORY") != REPO
            or int(os.environ.get("GITHUB_RUN_ID", "0")) != args.run_id):
        deny("MAIN_1")
    # Already-claimed attempt proof only. A pre-admission failure is not an attempt.
    proof = args.feedback.parent / "attempt-proof.json"
    if not proof.is_file() or proof.is_symlink():
        print("FEEDBACK_NO_SPENT_ATTEMPT")
        return
    data = json.loads(proof.read_text("utf-8"))
    if (data.get("task_id") != args.task or data.get("attempt") != args.attempt
            or data.get("run_id") != args.run_id):
        deny("MAIN_2")
    feedback = read_public(args.feedback, args.attempt)
    status = "PASS" if args.outcome == "success" else "BLOCKED_OR_FAILED"
    replay = os.environ.get("NATIVE_ROUTE_RETRY") == "true"
    print(publish(_subprocess, lambda path: _api(REPO, path), REPO,
                  args.control, args.task, args.sha, args.attempt, feedback, status,
                  route_replay_run_id=(args.run_id if replay else None)))


if __name__ == "__main__":
    try:
        main()
    except FeedbackBlocked as exc:
        print(str(exc), file=__import__("sys").stderr)
        raise SystemExit(1)
