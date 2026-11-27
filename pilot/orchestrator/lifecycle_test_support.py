"""Shared lifecycle API doubles; stdlib only, safe for unittest and pytest."""
import base64
import json
from pathlib import Path
from urllib.error import HTTPError

from pilot.orchestrator import request_lifecycle as life

MERGE = "a" * 40
HEAD = "b" * 40
PARENT = "c" * 40
SLUG = "req-123"
OTHER = "req-456"
CONTROL = life.CONTROL_PATH


def content(entries):
    data = json.dumps({"schema_version": life.CONTROL_SCHEMA, "requests": entries}).encode()
    return {"type": "file", "encoding": "base64", "size": len(data),
            "content": base64.b64encode(data).decode()}


TEST_MAIN = "e" * 40


def main_response(path, root=None, revision=TEST_MAIN):
    """Explicit offline GitHub main snapshot transport (not a production bypass)."""
    if path == "git/ref/heads/main":
        return {"ref": "refs/heads/main", "object": {"type": "commit", "sha": revision}}
    if path.startswith("contents/") and path.endswith("?ref=" + revision):
        relative = path[len("contents/"):].split("?ref=", 1)[0]
        file = Path(root) / relative if root is not None else None
        if file is not None and file.is_file() and not file.is_symlink():
            raw = file.read_bytes()
            return {"type": "file", "encoding": "base64", "size": len(raw),
                    "content": base64.b64encode(raw).decode()}
        raise HTTPError(path, 404, "Not found", {}, None)
    raise AssertionError(path)


def evidence_fixture(request, lot, sha, changed=()):
    from pilot.orchestrator.pg37_evidence import digest, STAGES
    row = {"schema_version": "CP37_LOT_EVIDENCE_V1", "request_id": request,
           "lot_id": lot, "merge_sha": sha, "changed_paths": sorted(changed),
           "analysis_sha256": "0" * 64, "packet_sha256": "1" * 64,
           "production_authority": False, "handoff_allowed": False,
           "requirements": {"status": "BLOCKED"}, "complete": False,
           "stages": {stage: {"status": "BLOCKED", "reason_code": "FIXTURE",
                               "production_authority": False}
                      for stage in sorted(set(STAGES) | {"PG-07"})}}
    row["evidence_sha256"] = digest(row)
    return row


def fake_api(entries, *, historical=None, issue_state="open", root=None, reopened=False):
    def prior():
        return {slug: {"state": {life.SUSPENDED: life.SUSPENDING, "ACTIVE": life.SUSPENDED}[entry["state"]],
                       "authorization_pr": 76}
                for slug, entry in entries.items() if entry["state"] != life.SUSPENDING}
    def api(path):
        if path.startswith("issues/") and path.split("/")[-1].isdigit():
            return {"number": int(path.split("/")[1]), "state": issue_state,
                    "labels": [{"name": "lf-request-blocked"}]}
        if path == f"contents/{CONTROL}?ref=main":
            return content(entries)
        if path == f"contents/{CONTROL}?ref={MERGE}":
            return content(entries if historical is None else historical)
        if path == f"contents/{CONTROL}?ref={PARENT}":
            return content(prior())
        if path == f"commits/{MERGE}":
            return {"sha": MERGE, "parents": [{"sha": PARENT}, {"sha": HEAD}],
                    "commit": {"message": "Merge PR #77 via sandbox-train"}}
        if path == "pulls/77":
            return {"number": 77, "merged": True, "merge_commit_sha": MERGE,
                    "merged_at": "2026-11-27T06:00:00Z",
                    "base": {"ref": "main", "repo": {"full_name": "example/sandbox"}},
                    "head": {"sha": HEAD, "repo": {"full_name": "example/sandbox"}}}
        if path == "pulls/77/reviews?per_page=100&page=1":
            return [{"id": 1, "user": {"login": "example"}, "state": "COMMENTED",
                     "commit_id": HEAD, "submitted_at": "2026-11-27T05:59:00Z",
                     "body": life.transition_marker(slug, prior().get(slug, {}).get("state", "ACTIVE"),
                                                    entry["state"], HEAD)}
                    for slug, entry in entries.items()]
        if path.startswith("actions/runs?status="):
            return {"total_count": 0, "workflow_runs": []}
        if path.startswith("issues?state=open&labels=examiner-working"):
            return []
        if path == "issues/77/events?per_page=100&page=1":
            return [{"event": "labeled", "actor": {"login": "example"}, "label": {"name": "ready-to-merge"}}]
        if path.startswith("issues/") and "/events?per_page=100&page=" in path:
            return [{"id": 999, "event": "closed"}] if reopened else []
        return main_response(path, root)
    return api
