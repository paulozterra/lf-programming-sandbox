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
# Resolve the trusted repository package for direct script execution.
import sys as _project_sys
from pathlib import Path as _project_Path
_project_sys.path.insert(0, str(_project_Path(__file__).resolve().parents[2]))
from pilot.config.project_config import storage_path, storage

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
    meta = sorted((storage_path("requests_root", root=ROOT)).glob(f"*/proposal_requests/{task}.proposal-request.json"))
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


def preacceptance_failure(feedback: dict) -> str:
    """Only the exact, single pre-acceptance signature rejection is eligible."""
    from native_feedback_delivery import parse_feedback

    if not isinstance(feedback, dict):
        deny("FEEDBACK_KIND")
    feedback = parse_feedback(json.dumps(feedback).encode("utf-8"), feedback.get("attempt"))
    rows = feedback["commands"]
    if len(rows) != 1:
        deny("NOT_A_SINGLE_TOOL_FAILURE")
    row = rows[0]
    reason = row.get("reason")
    if (row.get("name") != "reuse-component-guard" or row.get("status") != "FAIL"
            or row.get("returncode") != 1
            or row.get("stderr_excerpt") != "" or row.get("stdout_excerpt") != ""
            or not isinstance(reason, str)
            or re.fullmatch(r"DUPLICA_COMPONENTE_EXISTENTE:signature:[A-Za-z0-9_./-]+", reason) is None):
        deny("NOT_A_PREACCEPTANCE_SIGNATURE_FAILURE")
    return reason


def replay_preacceptance(source_base: str, control_sha: str, proposal: dict, spec: dict) -> str | None:
    """Same source, patch, context and writable scope; only trusted control changes."""
    with tempfile.TemporaryDirectory(prefix="t37-preacceptance-") as tmp:
        source, control = Path(tmp) / "source", Path(tmp) / "control"
        sh("git", "worktree", "add", "--detach", str(source), source_base)
        try:
            sh("git", "worktree", "add", "--detach", str(control), control_sha)
            try:
                input_file = Path(tmp) / "input.json"
                input_file.write_text(json.dumps({"proposal": proposal, "spec": spec}), "utf-8")
                # Execute only trusted control modules; proposal bytes are data.
                script = r"""
import json, pathlib, re, sys
control, source, input_file = map(pathlib.Path, sys.argv[1:])
sys.path[:0] = [str(control), str(control / 'pilot/worker_v08'),
                str(control / 'vendor/programming-agent/src')]
from pilot.worker_v08.reuse_guard import check, DuplicateComponent
from programming_agent_runner.hashutil import strict_json_loads
from programming_agent_runner.worker_patch import parse_patch_proposal, inspect_patch
from programming_agent_runner.worker_spec import parse_worker_task
data = json.loads(input_file.read_text('utf-8'))
spec = data['spec']
paths = spec['context_path_patterns']
reports = [p for p in paths if isinstance(p, str) and re.fullmatch(
    r'pilot/runs/[a-z][a-z0-9_-]{0,63}/reuse_assessment[.]json', p)]
if len(reports) != 1:
    raise ValueError('REPORT_NOT_UNIQUE')
report = source / reports[0]
if report.is_symlink() or not report.is_file():
    raise ValueError('REPORT_INVALID')
doc = strict_json_loads(report.read_text('utf-8'))
if doc.get('schema_version') != 'T7_REUSE_ASSESSMENT_V1' or not isinstance(doc.get('obligations'), list):
    raise ValueError('REPORT_INVALID')
ctx = []
for row in doc['obligations']:
    if not isinstance(row, dict) or not isinstance(row.get('reuse_context'), list):
        raise ValueError('REPORT_INVALID')
    for ref in row['reuse_context']:
        if isinstance(ref, dict) and ref.get('path') in paths:
            ctx.append(ref)
proposal = parse_patch_proposal(data['proposal'], parse_worker_task(spec))
patch = proposal.patch
inspect_patch(proposal, parse_worker_task(spec))
try:
    check(source, patch, ctx, writable=spec.get('write_path_patterns', []))
except DuplicateComponent as exc:
    print(json.dumps({'reason': str(exc)[:500]}))
else:
    print(json.dumps({'reason': None}))
"""
                result = subprocess.run([sys.executable, "-I", "-c", script,
                    str(control), str(source), str(input_file)], cwd=control,
                    capture_output=True, text=True, timeout=300)
                if result.returncode:
                    deny("PREACCEPTANCE_REPLAY_FAILED")
                reply = json.loads(result.stdout)
                if set(reply) != {"reason"} or (reply["reason"] is not None
                        and not isinstance(reply["reason"], str)):
                    deny("PREACCEPTANCE_REPLAY_INVALID")
                return reply["reason"]
            finally:
                sh("git", "worktree", "remove", "--force", str(control))
        finally:
            sh("git", "worktree", "remove", "--force", str(source))


def prove_preacceptance(task: str, run_ids: list[int], current_control: str, reason: str) -> dict:
    from native_route_tool_defect import PREACCEPTANCE_SCHEMA, PREACCEPTANCE_TOOL
    if (not TASK.fullmatch(task) or not SHA40.fullmatch(current_control)
            or not 1 <= len(run_ids) <= 3 or len(set(run_ids)) != len(run_ids)
            or not reason.strip()):
        deny("INPUT_INVALID")
    # Current tool must be a trusted main ancestor, never a proposal branch.
    if subprocess.run(["git", "merge-base", "--is-ancestor", current_control, "origin/main"],
                      cwd=ROOT).returncode:
        deny("CONTROL_NOT_TRUSTED_MAIN")
    reg_path = f"pilot/worker_v08/native_tasks/{task}.json"
    reg = json.loads(sh("git", "show", f"origin/main:{reg_path}"))
    base = reg["task_spec"]["base_head_sha"]
    meta = sorted(storage_path("requests_root", root=ROOT).glob(
        f"*/proposal_requests/{task}.proposal-request.json"))
    if len(meta) != 1:
        deny("REQUEST_NOT_FOUND")
    issue = int(meta[0].parts[-3].split("-", 1)[1])
    old_control = None
    rows = []
    for run_id in run_ids:
        run = api(f"actions/runs/{run_id}")
        identity = _run_identity(run, REPO)
        if (run.get("id") != run_id or run.get("conclusion") != "failure"
                or run.get("status") != "completed" or run.get("run_attempt") != 1
                or identity is None or identity[0] != task):
            deny("RUN_NOT_A_FAILED_ATTEMPT")
        control = run.get("head_sha")
        if (not isinstance(control, str) or not SHA40.fullmatch(control)
                or control == current_control or old_control not in (None, control)
                or subprocess.run(["git", "merge-base", "--is-ancestor", control, current_control],
                                  cwd=ROOT).returncode):
            deny("CONTROL_HISTORY_INVALID")
        old_control = control
        if json.loads(sh("git", "show", f"{control}:{reg_path}")) != reg:
            deny("REGISTRATION_CHANGED")
        sha = identity[1]
        feedback = feedback_for(issue, task, sha)
        expected = preacceptance_failure(feedback)
        sh("git", "fetch", "-q", "--no-tags", "origin", sha)
        env = json.loads(sh("git", "show", f"{sha}:pilot/native_proposals/{task}.json"))
        request = json.loads(sh("git", "show", f"{control}:{meta[0].relative_to(ROOT).as_posix()}"))
        if env.get("author") != "GPT_NATIVE" or env.get("task_pack_sha256") != request.get("task_pack_sha256"):
            deny("PROPOSAL_PACK_MISMATCH")
        from native_proposal_client import read_proposal_envelope
        with tempfile.TemporaryDirectory(prefix="t37-envelope-") as tmp:
            envelope = Path(tmp) / "proposal.json"
            envelope.write_text(json.dumps(env), "utf-8")
            validated = read_proposal_envelope(envelope)
        proposal = validated["proposal"]
        if replay_preacceptance(base, control, proposal, reg["task_spec"]) != expected:
            deny("SUPERSEDED_TOOL_DOES_NOT_REPRODUCE")
        if replay_preacceptance(base, current_control, proposal, reg["task_spec"]) is not None:
            deny("CURRENT_TOOL_STILL_FAILS")
        rows.append({"run_id": run_id, "proposal_commit_sha": sha,
                     "task_pack_sha256": env["task_pack_sha256"]})
    old_sha = tool_sha(old_control, PREACCEPTANCE_TOOL)
    new_sha = tool_sha(current_control, PREACCEPTANCE_TOOL)
    if old_sha == new_sha:
        deny("TOOL_UNCHANGED")
    return {"schema_version": PREACCEPTANCE_SCHEMA, "task": task,
            "tool": PREACCEPTANCE_TOOL, "blocked_code": "DUPLICA_COMPONENTE_EXISTENTE",
            "base_head_sha": base, "superseded_control_sha": old_control,
            "current_control_sha": current_control, "superseded_tool_sha256": old_sha,
            "current_tool_sha256": new_sha, "forgiven": rows, "reason": reason}


def prove_patch(task: str, run_ids: list[int], reason: str) -> dict:
    """T38: each run's patch must not apply to the registered base."""
    from native_intake_defect import SCHEMA as INTAKE, CODE
    from native_proposal_push_guard import patch_applies
    if not TASK.fullmatch(task) or not run_ids:
        deny("INPUT_INVALID")
    reg = json.loads((storage_path("registrations_root", root=ROOT) / (task + ".json")).read_text("utf-8"))
    base = reg["task_spec"]["base_head_sha"]
    meta = sorted((storage_path("requests_root", root=ROOT)).glob(f"*/proposal_requests/{task}.proposal-request.json"))
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
    ap.add_argument("command", choices=["prove", "prove-patch", "prove-preacceptance"])
    ap.add_argument("--task", required=True)
    ap.add_argument("--run-id", type=int, action="append", required=True)
    ap.add_argument("--current-base")
    ap.add_argument("--reason", required=True)
    ap.add_argument("--registered-ref", default="origin/main")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    try:
        record = (prove_patch(a.task, a.run_id, a.reason) if a.command == "prove-patch"
                  else prove_preacceptance(a.task, a.run_id, a.current_base or "", a.reason)
                  if a.command == "prove-preacceptance"
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
