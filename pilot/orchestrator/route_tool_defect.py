"""T37: prove a route-tool defect and write its governed forgiveness record.

    python3 pilot/orchestrator/route_tool_defect.py prove \
        --task req286contrato1 --run-id 1 --run-id 2 --current-base <sha>

For each run it reads, from trusted sources only:
* the Worker run (GitHub): conclusion failure, proposal commit = head_sha;
* the bot's visible-feedback comment on the request Issue for that commit;
* the proposal envelope at that commit (patch + task_pack_sha256).

The visible failure must come only from a trusted route tool (ROUTE_TOOLS)
with one BLOCKED code. Then the proof re-executes that exact command on the
proposal applied to the registered (superseded) base, where it must fail with
the same code, and on the current base, where it must pass. Only then is the
record written. It never reads a hidden exam.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pilot/worker_v08"))
from native_route_defect import ROUTE_TOOLS, BLOCK  # noqa: E402
from native_route_tool_defect import SCHEMA, verified_route_tool_defects  # noqa: E402
from native_feedback_delivery import _run_identity  # noqa: E402

TASK = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
REPO = "paulozterra/lf-programming-sandbox"
PY = {"lf-python", "python", "python3", "python3.12"}


CODE_LINE = re.compile(r"BLOCKED:([A-Z][A-Z0-9_]{0,79})(?::[A-Za-z0-9_,.:/-]{0,200})?")


def code_of(text: str) -> str | None:
    """First BLOCKED code of a tool's stderr (literal '\\n' from JSON excerpts tolerated)."""
    first = (text or "").replace("\\n", "\n").strip().split("\n", 1)[0].strip()
    m = CODE_LINE.fullmatch(first)
    return m.group(1) if m else None


class ToolDefectBlocked(ValueError):
    pass


def deny(code: str):
    raise ToolDefectBlocked(code)


def sh(*args, cwd=ROOT, check=True) -> str:
    r = subprocess.run(list(args), cwd=cwd, capture_output=True, text=True)
    if check and r.returncode:
        deny("COMMAND_FAILED:" + " ".join(args[:3]))
    return r.stdout


def api(path: str):
    return json.loads(sh("gh", "api", f"repos/{REPO}/{path}"))


def api_list(path: str) -> list:
    rows = json.loads(sh("gh", "api", f"repos/{REPO}/{path}"))
    if not isinstance(rows, list):
        deny("GITHUB_COLLECTION_INVALID")
    return rows


def feedback_for(issue: int, task: str, sha: str) -> dict:
    marker = f"<!-- LF_NATIVE_VISIBLE_FEEDBACK:{task}:{sha}:"
    found = []
    for page in range(1, 6):
        rows = api_list(f"issues/{issue}/comments?per_page=100&page={page}")
        found += [c for c in rows if (c.get("user") or {}).get("login") == "github-actions[bot]"
                  and marker in (c.get("body") or "")]
        if len(rows) < 100:
            break
    if len(found) != 1:
        deny("FEEDBACK_NOT_UNIQUE")
    body = found[0]["body"]
    m = re.search(r"```json\n(.*?)\n```", body, re.S)
    if not m:
        deny("FEEDBACK_UNPARSEABLE")
    return json.loads(m.group(1))


def failing_tool(feedback: dict, record: dict) -> tuple[dict, str]:
    if feedback.get("kind") != "VISIBLE_ACCEPTANCE_ONLY":
        deny("FEEDBACK_KIND")
    by_name = {c["name"]: c for c in record["task_spec"]["acceptance_commands"]}
    failed = [c for c in feedback.get("commands", []) if c.get("status") == "FAIL"]
    if len(failed) != 1:
        deny("NOT_A_SINGLE_TOOL_FAILURE")
    row = failed[0]
    cmd = by_name.get(row.get("name"))
    if (cmd is None or len(cmd["argv"]) < 2 or cmd["argv"][0] not in PY
            or cmd["argv"][1] not in ROUTE_TOOLS or row.get("reason") != "EXIT_NONZERO"):
        deny("FAILURE_NOT_FROM_ROUTE_TOOL")
    code = code_of(row.get("stderr_excerpt") or "")
    if code is None:
        deny("FAILURE_NOT_BLOCKED_CODE")
    return cmd, code


def replay(base: str, patch: str, argv: list[str]) -> tuple[int, str]:
    with tempfile.TemporaryDirectory(prefix="t37-") as tmp:
        tree = Path(tmp) / "tree"
        sh("git", "worktree", "add", "--detach", str(tree), base)
        try:
            p = Path(tmp) / "p.patch"
            p.write_text(patch, "utf-8")
            if subprocess.run(["git", "apply", str(p)], cwd=tree).returncode:
                deny("PATCH_DOES_NOT_APPLY")
            r = subprocess.run([sys.executable] + argv[1:], cwd=tree,
                               capture_output=True, text=True, timeout=300)
            return r.returncode, (r.stderr or "").strip()
        finally:
            sh("git", "worktree", "remove", "--force", str(tree))


def tool_sha(base: str, tool: str) -> str:
    return hashlib.sha256(subprocess.run(["git", "show", f"{base}:{tool}"], cwd=ROOT,
                                         capture_output=True, check=True).stdout).hexdigest()


def prove(task: str, run_ids: list[int], current_base: str, reason: str,
          registered_ref: str = "origin/main") -> dict:
    """registered_ref: the commit whose registration the failed runs used."""
    if not TASK.fullmatch(task) or not SHA40.fullmatch(current_base) or not run_ids:
        deny("INPUT_INVALID")
    reg = json.loads(sh("git", "show", f"{registered_ref}:pilot/worker_v08/native_tasks/{task}.json"))
    old_base = reg["task_spec"]["base_head_sha"]
    if old_base == current_base:
        deny("BASE_NOT_CHANGED")
    meta = sorted((ROOT / "pilot/runs").glob(f"*/proposal_requests/{task}.proposal-request.json"))
    if len(meta) != 1:
        deny("REQUEST_NOT_FOUND")
    issue = int(meta[0].parts[-3].split("-", 1)[1])
    tool = code = None
    rows = []
    for run_id in run_ids:
        run = api(f"actions/runs/{run_id}")
        identity = _run_identity(run, REPO)
        if run.get("conclusion") != "failure" or identity is None or identity[0] != task:
            deny("RUN_NOT_A_FAILED_ATTEMPT")
        sha = identity[1]
        cmd, blocked = failing_tool(feedback_for(issue, task, sha), reg)
        if tool not in (None, cmd["argv"][1]) or code not in (None, blocked):
            deny("RUNS_DISAGREE")
        tool, code = cmd["argv"][1], blocked
        sh("git", "fetch", "-q", "--no-tags", "origin", sha)
        env = json.loads(sh("git", "show", f"{sha}:pilot/native_proposals/{task}.json"))
        patch = env["proposal"]["patch"]
        rc_old, err_old = replay(old_base, patch, cmd["argv"])
        if rc_old == 0 or code_of(err_old) != blocked:
            deny("SUPERSEDED_TOOL_DOES_NOT_REPRODUCE")
        rc_new, _ = replay(current_base, patch, cmd["argv"])
        if rc_new != 0:
            deny("CURRENT_TOOL_STILL_FAILS")
        rows.append({"run_id": run_id, "proposal_commit_sha": sha,
                     "task_pack_sha256": env["task_pack_sha256"]})
    old_sha, new_sha = tool_sha(old_base, tool), tool_sha(current_base, tool)
    if old_sha == new_sha:
        deny("TOOL_UNCHANGED")
    return {"schema_version": SCHEMA, "task": task, "tool": tool, "blocked_code": code,
            "superseded_base_sha": old_base, "current_base_sha": current_base,
            "superseded_tool_sha256": old_sha, "current_tool_sha256": new_sha,
            "forgiven": rows, "reason": reason}


def prove_patch(task: str, run_ids: list[int], reason: str) -> dict:
    """T38: each run's patch must not apply to the registered base."""
    from native_intake_defect import SCHEMA as INTAKE, CODE
    from native_proposal_push_guard import patch_applies
    if not TASK.fullmatch(task) or not run_ids:
        deny("INPUT_INVALID")
    reg = json.loads((ROOT / "pilot/worker_v08/native_tasks" / (task + ".json")).read_text("utf-8"))
    base = reg["task_spec"]["base_head_sha"]
    meta = sorted((ROOT / "pilot/runs").glob(f"*/proposal_requests/{task}.proposal-request.json"))
    if len(meta) != 1:
        deny("REQUEST_NOT_FOUND")
    issue = int(meta[0].parts[-3].split("-", 1)[1])
    rows = []
    for run_id in run_ids:
        run = api(f"actions/runs/{run_id}")
        identity = _run_identity(run, REPO)
        if run.get("conclusion") != "failure" or identity is None or identity[0] != task:
            deny("RUN_NOT_A_FAILED_ATTEMPT")
        sha = identity[1]
        if feedback_for(issue, task, sha).get("commands") != []:
            deny("ACCEPTANCE_RAN")
        sh("git", "fetch", "-q", "--no-tags", "origin", sha)
        env = json.loads(sh("git", "show", f"{sha}:pilot/native_proposals/{task}.json"))
        if patch_applies(ROOT, base, env["proposal"]["patch"]):
            deny("PATCH_APPLIES")
        rows.append({"run_id": run_id, "proposal_commit_sha": sha,
                     "task_pack_sha256": env["task_pack_sha256"]})
    return {"schema_version": INTAKE, "task": task, "code": CODE, "base_head_sha": base,
            "forgiven": rows, "reason": reason}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["prove", "prove-patch"])
    ap.add_argument("--task", required=True)
    ap.add_argument("--run-id", type=int, action="append", required=True)
    ap.add_argument("--current-base")
    ap.add_argument("--reason", required=True)
    ap.add_argument("--registered-ref", default="origin/main")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    try:
        record = (prove_patch(a.task, a.run_id, a.reason) if a.command == "prove-patch"
                  else prove(a.task, a.run_id, a.current_base or "", a.reason, a.registered_ref))
    except (ToolDefectBlocked, subprocess.CalledProcessError, KeyError, ValueError) as exc:
        print("T37_BLOCKED:" + str(exc), file=sys.stderr)
        return 1
    text = json.dumps(record, indent=2, sort_keys=True) + "\n"
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(text, "utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
