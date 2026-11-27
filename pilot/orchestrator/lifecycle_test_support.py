"""Shared lifecycle API doubles; stdlib only, safe for unittest and pytest."""
import base64
import json

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


def fake_api(entries, *, historical=None, issue_state="open"):
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
        raise AssertionError(path)
    return api


