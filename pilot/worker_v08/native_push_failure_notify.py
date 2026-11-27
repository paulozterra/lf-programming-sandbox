"""Trusted-main bot issue notifier for a rejected native proposal push."""
from __future__ import annotations
# Resolve the trusted repository package for direct script execution.
import sys as _project_sys
from pathlib import Path as _project_Path
_project_sys.path.insert(0, str(_project_Path(__file__).resolve().parents[2]))
from pilot.config.project_config import storage_path, storage
import argparse
import json
from pathlib import Path
import re
import subprocess

REPO = "paulozterra/lf-programming-sandbox"
BOT = "41898282+github-actions[bot]@users.noreply.github.com"


def command(*args):
    return subprocess.run(args, check=True, capture_output=True,
                          text=True, timeout=30).stdout.strip()


def find_issue(control, task):
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", task):
        return None
    paths = command("git", "-C", str(control), "ls-tree", "-r", "--name-only",
                    "HEAD", "--", storage()["requests_root"]).splitlines()
    pattern = r"pilot/runs/req-[1-9][0-9]*/proposal_requests/" + re.escape(task) + r"\.proposal-request\.json"
    matches = [p for p in paths if re.fullmatch(pattern, p)]
    if len(matches) != 1:
        return None
    slug = matches[0].split("/")[2]
    num = int(slug[4:])
    meta_path = f"pilot/runs/{slug}/request_meta.json"
    try:
        meta = json.loads(command("git", "-C", str(control), "show", "HEAD:" + meta_path))
        info = json.loads(command("git", "-C", str(control), "show", "HEAD:" + matches[0]))
        author = command("git", "-C", str(control), "log", "-1", "--format=%ae",
                         "--", meta_path)
    except (ValueError, subprocess.CalledProcessError):
        return None
    if (meta.get("issue") != num or author != BOT
            or info.get("task_name") != task
            or info.get("branch") != "lf/native-proposal/" + task):
        return None
    return num


def notify(control, branch, sha, code):
    if not re.fullmatch(r"[0-9a-f]{40}", sha) or not re.fullmatch(r"NATIVE_[A-Z0-9_]{1,90}", code):
        return "NATIVE_PUSH_ALERT_INPUT_INVALID"
    if not branch.startswith("lf/native-proposal/"):
        return "NATIVE_PUSH_ALERT_BRANCH_INVALID"
    task = branch.removeprefix("lf/native-proposal/")
    number = find_issue(control, task)
    if number is None:
        return "NATIVE_PUSH_ALERT_UNMAPPED"
    issue = json.loads(command("gh", "api", f"repos/{REPO}/issues/{number}"))
    # T38.1 (as T35): identity is proven by find_issue (bot-written request_meta
    # on trusted main); API-created issues carry no lf-request label.
    if (issue.get("number") != number or issue.get("state") != "open"
            or issue.get("pull_request")):
        return "NATIVE_PUSH_ALERT_ISSUE_UNVERIFIED"
    from pilot.orchestrator.request_lifecycle import request_state, OPEN, inactive_reason, RequestStateError
    def lifecycle():
        try:
            state = request_state(f"req-{number}", lambda path: json.loads(
                command("gh", "api", f"repos/{REPO}/{path}")), root=Path(control))
            return None if state == OPEN else inactive_reason(state)
        except RequestStateError:
            return "REQUEST_STATE_UNRESOLVED"
    stop = lifecycle()
    if stop:
        return stop
    marker = f"<!-- LF_NATIVE_PUSH_REJECTED:{task}:{sha}:{code} -->"
    comments = json.loads(command("gh", "api",
                           f"repos/{REPO}/issues/{number}/comments?per_page=100"))
    if not isinstance(comments, list) or len(comments) >= 100:
        return "NATIVE_PUSH_ALERT_COMMENTS_UNAVAILABLE"
    if any(marker in str(c.get("body", "")) for c in comments
           if isinstance(c, dict) and (c.get("user") or {}).get("login") == "github-actions[bot]"):
        return "NATIVE_PUSH_ALERT_ALREADY_SENT"
    expected = "pilot/native_proposals/" + task + ".json"
    if code == "NATIVE_PUSH_PATCH_NOT_APPLICABLE":
        body = (marker + "\nWorker push rechazado: " + code + ". "
                "El campo proposal.patch de " + expected + " no se aplica con "
                "`git apply --check` sobre la base registrada del lote (task_spec.base_head_sha "
                "en pilot/worker_v08/native_tasks/" + task + ".json). "
                "No se ejecutó el Worker y NO se cobró intento. "
                "Genera el parche con `git diff` desde esa base y vuelve a enviarlo.")
        stop = lifecycle()
        if stop:
            return stop
        command("gh", "issue", "comment", str(number), "--repo", REPO, "--body", body)
        return "NATIVE_PUSH_ALERT_COMMENTED"
    body = (marker + "\nWorker push rechazado: " + code + ". "
            "Se esperaba UN archivo " + expected +
            " con exactamente task_pack_sha256, proposal_sha256, proposal, author=GPT_NATIVE. "
            "La rama debe partir del main confiable actual, todos sus commits "
            "modificar exclusivamente ese sobre; no se admite el push de archivos fuente. "
            "Ver submission en pilot/runs/req-" + str(number) +
            "/proposal_requests/" + task + ".proposal-request.json. "
            "No se ejecutó ningún archivo del push.")
    stop = lifecycle()
    if stop:
        return stop
    command("gh", "issue", "comment", str(number), "--repo", REPO, "--body", body)
    return "NATIVE_PUSH_ALERT_COMMENTED"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--code", required=True)
    a = parser.parse_args()
    print(notify(a.control, a.branch, a.sha, a.code))


if __name__ == "__main__":
    main()
