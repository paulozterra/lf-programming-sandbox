#!/usr/bin/env python3
"""A5: deterministic steps around the event-driven auditor (audit-auditor.yml).

The model audits in a step with no GitHub credential. Everything that reads
GitHub or changes it is here, as code, not as model decisions:

  prepare  --issue N   check the issue (bot-authored, labelled, marked, open, no
                       audit yet), write audit_input_v2.json, emit request/project
  finalize --request R only paths under pilot/runs/R/audit/ changed; assemble the
                       report from draft.json; skill validator + route checks pass
  publish  --request R --issue N   push branch audit-R, open the PR, comment the
                       issue, dispatch CI for the head
  land     --pr P      wait for every check on the head; all green -> label
                       ready-to-merge and dispatch the train; otherwise comment
"""
from __future__ import annotations
# Direct-script entrypoint: resolve the trusted repository root from this file,
# not from the caller's working directory or PYTHONPATH.
import sys as _project_sys
from pathlib import Path as _project_Path
_project_sys.path.insert(0, str(_project_Path(__file__).resolve().parents[2]))
from pilot.config.project_config import storage_path, storage
from pilot.audit import audit_lifecycle as al
from pilot.orchestrator.request_lifecycle import RequestStateError

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
LABEL = "audit-request"
BOT = "github-actions[bot]"
MARK = re.compile(r"<!-- audit-request:(req-[a-z0-9-]{1,60}) -->")
TITLE = re.compile(r"^\[AUDIT\]\[([a-z0-9_-]{1,40})\] ")
FENCE = re.compile(r"```json\n(.*?)\n```", re.S)


class JobError(RuntimeError):
    pass


def gh(*args: str, data: dict | None = None) -> str:
    cmd = ["gh", "api", *args] + (["--input", "-"] if data is not None else [])
    out = subprocess.run(cmd, input=json.dumps(data) if data is not None else None,
                         capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise JobError("AUDITOR_GITHUB_FAILED")
    return out.stdout


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True).stdout


def parse_issue(issue: dict) -> tuple[str, str, dict]:
    """Pure: accept only route-bot issues carrying one audit request."""
    if issue.get("state") != "open":
        raise JobError("AUDITOR_ISSUE_NOT_OPEN")
    if (issue.get("user") or {}).get("login") != BOT:
        raise JobError("AUDITOR_ISSUE_NOT_FROM_ROUTE")
    if LABEL not in {l.get("name") for l in issue.get("labels", [])}:
        raise JobError("AUDITOR_ISSUE_NOT_LABELLED")
    body = issue.get("body") or ""
    marks, title, fence = MARK.findall(body), TITLE.match(issue.get("title") or ""), FENCE.findall(body)
    if len(marks) != 1 or not title or len(fence) != 1:
        raise JobError("AUDITOR_ISSUE_MALFORMED")
    data = al.strict_json(fence[0])
    if data.get("schema_version") != "LF_DEEP_AUDIT_INPUT_V2" or \
            data.get("evidence_destination") != f"pilot/runs/{marks[0]}/audit":
        raise JobError("AUDITOR_INPUT_MISMATCH")
    return marks[0], title.group(1), data


def changed_outside(request: str, paths: list[str]) -> list[str]:
    """Pure: every changed path must live under the request's audit folder."""
    prefix = f"pilot/runs/{request}/audit/"
    return sorted(p for p in paths if not p.startswith(prefix))


def live_reader(repo):
    return lambda path: json.loads(gh(f"repos/{repo}/" + path))


def prepare(issue_number: int, repo: str) -> dict:
    reader = live_reader(repo)
    request, project, data = al.require_audit_issue(issue_number, repo, reader, root=ROOT)
    if (ROOT / data["evidence_destination"]).exists():
        raise JobError("AUDITOR_AUDIT_ALREADY_PRESENT")
    if json.loads(gh(f"repos/{repo}/pulls?state=open&head={repo.split('/')[0]}:audit-{request}")):
        raise JobError("AUDITOR_PR_ALREADY_OPEN")
    out = ROOT / data["evidence_destination"]
    if al.require_audit_issue(issue_number, repo, reader, root=ROOT,
                              expected_request=request, expected_project=project)[2] != data:
        raise JobError("AUDITOR_INPUT_CHANGED")
    out.mkdir(parents=True)
    (out / "audit_input_v2.json").write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    (out / "cohort_sample.json").write_text('{"rows": []}\n')
    return {"request": request, "project": project}


def finalize(request: str, project: str, skill_dir: Path) -> dict:
    status = [line[3:] for line in git("status", "--porcelain", "--untracked-files=all").splitlines()]
    outside = changed_outside(request, status)
    if outside:
        raise JobError("AUDITOR_WROTE_OUTSIDE_AUDIT_DIR:" + outside[0])
    audit = storage_path("requests_root", root=ROOT) / request / "audit"
    import report_scaffold as rs
    report = rs.assemble(json.loads((audit / "draft.json").read_text()),
                         json.loads((audit / "audit_input_v2.json").read_text()), skill_dir)
    (audit / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    import validate_report as vr
    errors = vr.validate(audit / "report.json", skill_dir, ROOT, None)
    if errors:
        raise JobError("AUDITOR_REPORT_INVALID:" + ";".join(errors[:5]))
    f = report["findings"]
    return {"findings": len(f), "confirmed": sum(x["status"] == "CONFIRMED" for x in f),
            "rules": len(report["audit_tasks"])}


def publish(request: str, project: str, issue: int, repo: str, summary: dict) -> int:
    branch = f"audit-{request}"
    reader = live_reader(repo)
    initial = al.require_audit_issue(issue, repo, reader, root=ROOT,
                                     expected_request=request, expected_project=project)[2]
    def guard():
        if al.require_audit_issue(issue, repo, reader, root=ROOT,
                                  expected_request=request, expected_project=project)[2] != initial:
            raise JobError("AUDITOR_INPUT_CHANGED")
    git("checkout", "-b", branch)
    git("add", f"pilot/runs/{request}/audit")
    git("-c", f"user.name={BOT}", "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
        "commit", "-qm", f"[AUDIT][{project}] {request}: informe de auditoría (SHADOW)")
    # Also inspect committed changes: a clean worktree is not proof of scope.
    parts = git("diff", "--name-status", "--no-renames", "-z", "origin/main...HEAD").split("\0")
    if not parts or parts.pop() != "" or len(parts) % 2 or any(
            status != "A" for status in parts[::2]):
        raise JobError("AUDITOR_COMMIT_SCOPE_INVALID")
    prefix = al.scope(request, parts[1::2])
    from pilot.audit.historical_evidence import tree_blob
    head = git("rev-parse", "HEAD").strip()
    if al.strict_json(tree_blob(ROOT, head, prefix + "audit_input_v2.json")) != initial:
        raise JobError("AUDITOR_INPUT_CHANGED")
    ctx = al.strict_json(tree_blob(ROOT, head, prefix + "report.json")).get("audit_context", {})
    if ctx.get("source_revision") != initial["base_commit"] or ctx.get("promotion_authorized") is not False:
        raise JobError("AUDITOR_REPORT_PROVENANCE_INVALID")
    # Reject symlinks/submodules even when they are under the audit directory.
    for name in parts[1::2]:
        tree_blob(ROOT, head, name)
    guard()
    token = os.environ["GH_TOKEN"]
    subprocess.run(["git", "-C", str(ROOT), "push", "-q",
                    f"https://x-access-token:{token}@github.com/{repo}.git", f"HEAD:refs/heads/{branch}"],
                   check=True, capture_output=True)
    guard()
    pr = json.loads(gh(f"repos/{repo}/pulls", data={
        "title": f"[AUDIT][{project}] {request}", "head": branch, "base": "main",
        "body": f"Auditoría automática del pedido `{request}` (issue #{issue}). Auditor: Claude, sin credencial de GitHub.\n\n"
                f"Reglas: {summary['rules']} · hallazgos: {summary['findings']} ({summary['confirmed']} confirmados).\n"
                "Validado antes de publicar (skill V2 + controles de la ruta); el CI añade el EKB en vivo. Modo SHADOW."}))
    al.require_audit_pr(pr, reader, root=ROOT)
    guard()
    gh(f"repos/{repo}/issues/{issue}/comments", data={"body":
       f"Informe en el PR #{pr['number']}: {summary['rules']} reglas, {summary['findings']} hallazgos "
       f"({summary['confirmed']} confirmados con reproductor). Se fusionará solo si el CI pasa."})
    for workflow in ("ci.yml", "audit-stage.yml"):
        al.require_audit_pr(pr, reader, root=ROOT)
        guard()
        gh("-X", "POST", f"repos/{repo}/actions/workflows/{workflow}/dispatches",
           data={"ref": branch, **({"inputs": {"project": project}} if workflow == "audit-stage.yml" else {})})
    return pr["number"]


def land(pr_number: int, repo: str, timeout_s: int = 3600) -> str:
    reader = live_reader(repo)
    pr = reader(f"pulls/{pr_number}")
    def guard():
        al.require_audit_pr(pr, reader, root=ROOT)
    guard()
    head = pr["head"]["sha"]
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        runs = json.loads(gh(f"repos/{repo}/commits/{head}/check-runs?per_page=100"))["check_runs"]
        pending = [r for r in runs if r["status"] != "completed"]
        if len(runs) >= 5 and not pending:
            bad = sorted(r["name"] for r in runs if r["conclusion"] not in ("success", "skipped", "neutral"))
            if bad:
                guard()
                gh(f"repos/{repo}/issues/{pr_number}/comments",
                   data={"body": "CI no pasó: " + ", ".join(bad) + ". El informe queda abierto para revisión."})
                return "CI_FAILED"
            try:
                al.require_audit_check(reader, head)
            except RequestStateError as exc:
                if str(exc) != "AUDIT_STAGE_NOT_GREEN":
                    raise
                time.sleep(30)
                continue
            guard()
            gh(f"repos/{repo}/issues/{pr_number}/labels", data={"labels": ["ready-to-merge"]})
            al.require_audit_check(reader, head)
            guard()
            gh("-X", "POST", f"repos/{repo}/actions/workflows/sandbox-train.yml/dispatches",
               data={"ref": "main", "inputs": {"pr_number": str(pr_number)}})
            return "HANDED_TO_TRAIN"
        time.sleep(30)
    return "CI_TIMEOUT"


def notify_blocked(issue, repo):
    al.require_audit_issue(issue, repo, live_reader(repo), root=ROOT)
    gh(f"repos/{repo}/issues/{issue}/comments",
       data={"body": "La auditoría automática se detuvo; consultar la corrida A5."})
    return {"outcome": "AUDIT_BLOCKED_NOTIFIED"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["prepare", "finalize", "publish", "land", "notify-blocked"])
    ap.add_argument("--issue", type=int)
    ap.add_argument("--request")
    ap.add_argument("--project")
    ap.add_argument("--pr", type=int)
    ap.add_argument("--skill-dir", type=Path)
    ap.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    a = ap.parse_args()
    try:
        if a.action == "prepare":
            result = prepare(a.issue, a.repository)
        elif a.action == "finalize":
            result = finalize(a.request, a.project, a.skill_dir)
        elif a.action == "publish":
            summary = finalize(a.request, a.project, a.skill_dir)
            result = {"pr": publish(a.request, a.project, a.issue, a.repository, summary)}
        elif a.action == "land":
            result = {"outcome": land(a.pr, a.repository)}
        else:
            result = notify_blocked(a.issue, a.repository)
    except (JobError, OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)[:300]}))
        return 1
    print(json.dumps({"status": "OK", **result}))
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as fh:
            for k, v in result.items():
                fh.write(f"{k}={v}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
