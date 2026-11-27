#!/usr/bin/env python3
"""T48: open an audit request when a route request closes (REQUEST_CLOSED).

Generic per project: reads pilot/audit/projects/<project>.json. For every
request whose chain plan has all lots attested as integrated (the same proof
CP3.6 uses), and whose closing merge is not older than audit.since_commit,
opens one GitHub issue labelled `audit-request` carrying the derived
LF_DEEP_AUDIT_INPUT_V2. The auditor (a Claude routine, never the builder)
answers it with a PR under pilot/runs/<request>/audit/ that audit-stage.yml
validates. SHADOW mode: nothing here blocks a request.

Idempotent: a request with an existing audit directory or an existing
`audit-request` issue (open or closed) is skipped.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import build_input as bi  # noqa: E402
from audit_config import AuditConfigError, load  # noqa: E402
from pilot.orchestrator.request_lifecycle import require_finalized_audit, RequestStateError
from pilot.audit import audit_lifecycle as al
from pilot.config.project_config import storage, storage_path

LABEL = "audit-request"
MARK = "<!-- audit-request:{request} -->"


def gh(*args: str, data: dict | None = None) -> str:
    cmd = ["gh", "api", *args]
    if data is not None:
        cmd += ["--input", "-"]
    out = subprocess.run(cmd, input=json.dumps(data) if data is not None else None,
                         capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise RuntimeError("AUDIT_TRIGGER_GITHUB_FAILED")
    return out.stdout


def existing_requests(repo: str) -> set[str]:
    seen = set()
    for page in range(1, 11):
        items = json.loads(gh(f"repos/{repo}/issues?labels={LABEL}&state=all&per_page=100&page={page}"))
        for item in items:
            body = item.get("body") or ""
            if "<!-- audit-request:" in body:
                seen.add(body.split("<!-- audit-request:", 1)[1].split(" -->", 1)[0])
        if len(items) < 100:
            return seen
    raise RuntimeError("AUDIT_TRIGGER_PAGINATION")


def close_done(repo: str, root: Path = ROOT) -> list[dict]:
    """A4: close each open audit-request whose report is already on main."""
    closed = []
    items = json.loads(gh(f"repos/{repo}/issues?labels={LABEL}&state=open&per_page=100"))
    if len(items) >= 100:
        raise RuntimeError("AUDIT_TRIGGER_PAGINATION")
    for item in items:
        body = item.get("body") or ""
        if "<!-- audit-request:" not in body:
            continue
        req = body.split("<!-- audit-request:", 1)[1].split(" -->", 1)[0]
        report = storage_path("requests_root", req, root=root) / "audit/report.json"
        if not report.is_file():
            continue
        reader = lambda path: json.loads(gh(f"repos/{repo}/" + path))
        try:
            data = al.require_audit_issue(item["number"], repo, reader, root=root,
                                          expected_request=req)[2]
            from pilot.audit.historical_evidence import tree_blob
            main = subprocess.check_output(["git", "-C", str(root), "rev-parse",
                                            "refs/remotes/origin/main^{commit}"], text=True).strip()
            prefix = f"pilot/runs/{req}/audit/"
            if al.strict_json(tree_blob(root, main, prefix + "audit_input_v2.json")) != data:
                continue
            ctx = al.strict_json(tree_blob(root, main, prefix + "report.json")).get("audit_context", {})
            if ctx.get("source_revision") != data["base_commit"] or ctx.get("promotion_authorized") is not False:
                continue
        except (RequestStateError, OSError, ValueError, KeyError, subprocess.SubprocessError):
            continue
        head = subprocess.run(["git", "-C", str(root), "log", "-1", "--format=%H", "--", str(report)],
                              capture_output=True, text=True).stdout.strip()
        if al.require_audit_issue(item["number"], repo, reader, root=root, expected_request=req)[2] != data:
            raise RequestStateError("AUDIT_PROVENANCE_UNVERIFIED")
        gh(f"repos/{repo}/issues/{item['number']}/comments",
           data={"body": f"Informe de auditoría fusionado: `{storage()['requests_root']}/{req}/audit/report.json` (commit `{head}`). Se cierra."})
        if al.require_audit_issue(item["number"], repo, reader, root=root, expected_request=req)[2] != data:
            raise RequestStateError("AUDIT_PROVENANCE_UNVERIFIED")
        gh("-X", "PATCH", f"repos/{repo}/issues/{item['number']}", data={"state": "closed", "state_reason": "completed"})
        closed.append({"request": req, "issue": item["number"], "commit": head})
    return closed


def is_ancestor(older: str, newer: str, root: Path = ROOT) -> bool:
    return subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", older, newer],
                          capture_output=True).returncode == 0


def _finalized_request(request: str, repo: str, root: Path, api=None) -> bool:
    if not isinstance(repo, str) or "/" not in repo:
        raise RequestStateError("REQUEST_STATE_UNRESOLVED")
    transport = api or (lambda endpoint: json.loads(gh(f"repos/{repo}/" + endpoint)))
    try:
        require_finalized_audit(request, transport, root=root)
    except RequestStateError as exc:
        if str(exc) in ("AUDIT_REQUEST_NOT_FINALIZED", "REQUEST_SUSPENDED"):
            return False
        raise
    return True


def candidates(config: dict, plans, root: Path = ROOT, *, repository: str = "", api=None) -> list[str]:
    """Closed requests whose close is at or after since_commit."""
    import chain_lots as cl
    since = config["audit"].get("since_commit")
    out = []
    for req, lots, _state, bindings in plans:
        # Integrated lots alone do not prove the issue was closed by T9.
        if not _finalized_request(req, repository, root, api):
            continue
        ids = {lot["id"] for lot in lots.get("lots", [])}
        try:
            done = cl.completed_lots(lots, bindings, cl.first_parent_merges(req, root=root))
        except (SystemExit, ValueError, RuntimeError) as exc:  # one bad request never blocks the rest
            print(json.dumps({"event": "audit_trigger_skip", "request": req, "reason": str(exc)[:120]}),
                  file=sys.stderr)
            continue
        if not ids or set(done) != ids:
            continue
        close = bi.closing_merge([r["merge_sha"] for r in done.values()], root)
        if since and not is_ancestor(since, close, root):
            continue
        if (storage_path("requests_root", req, root=root) / "audit").exists():
            continue
        out.append(req)
    return sorted(out)


def issue_body(request: str, data: dict, config: dict) -> str:
    skill = config["audit"]["skill"]
    return "\n".join([
        MARK.format(request=request),
        f"Pedido cerrado: `{request}` · commit de cierre `{data['base_commit']}` · modo `{config['audit']['mode']}`.",
        "",
        f"Auditor: `{config['audit']['auditor']}` (nunca el constructor). Skill fijada: "
        f"`{skill['repository']}@{skill['commit']}` `{skill['path']}`.",
        "",
        f"Entregar en un PR: `{data['evidence_destination']}/audit_input_v2.json` (este JSON, sin cambios), "
        f"`report.json` (audit_report_v2) y la evidencia. `audit-stage.yml` lo valida.",
        "",
        "```json",
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
        "```",
    ])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    ap.add_argument("--request", help="force one request (ignores since_commit)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    try:
        config = load(a.project)
        audit = config["audit"]
        if not audit["enabled"] or audit["trigger"] != "REQUEST_CLOSED":
            print(json.dumps({"status": "AUDIT_TRIGGER_DISABLED"}))
            return 0
        import chain_lots as cl
        plans = cl.plans()
        if a.request:
            reqs = [a.request]
        else:
            reqs = candidates(config, plans, repository=a.repository)
        closed = [] if a.dry_run else close_done(a.repository)
        seen = set() if a.dry_run else existing_requests(a.repository)
        opened, skipped = [], []
        # A4: a forced or candidate request that is not opened always says why.
        skipped += [{"request": r, "reason": "AUDIT_SKIPPED:ALREADY_REQUESTED"} for r in reqs if r in seen]
        for req in [r for r in reqs if r not in seen][: max(1, int(audit.get("sample_n") or 1))]:
            if not _finalized_request(req, a.repository, ROOT):
                skipped.append({"request": req, "reason": "AUDIT_SKIPPED:REQUEST_NOT_FINALIZED"})
                continue
            lots, done = bi.completed_from_history(req)
            analysis = json.loads((storage_path("requests_root", req) / "analysis.json").read_text("utf-8"))
            data = bi.build(req, a.project, a.repository, done, lots, analysis)
            if a.dry_run:
                opened.append({"request": req, "base_commit": data["base_commit"]})
                continue
            # The issue can change while evidence is derived: recheck at publication.
            if not _finalized_request(req, a.repository, ROOT):
                skipped.append({"request": req, "reason": "AUDIT_SKIPPED:REQUEST_NOT_FINALIZED"})
                continue
            issue = json.loads(gh(f"repos/{a.repository}/issues", data={
                "title": f"[AUDIT][{a.project}] {req}", "labels": [LABEL],
                "body": issue_body(req, data, config)}))
            opened.append({"request": req, "issue": issue["number"]})
    except (AuditConfigError, bi.AuditInputError, RequestStateError, OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}))
        return 1
    print(json.dumps({"status": "AUDIT_TRIGGER_DONE", "opened": opened, "skipped": skipped, "closed": closed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
