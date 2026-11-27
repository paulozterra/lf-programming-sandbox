"""Shared lifecycle API doubles; stdlib only, safe for unittest and pytest."""
import base64
import json

from pilot.orchestrator import request_lifecycle as life

MERGE = "a" * 40
SLUG = "req-123"
OTHER = "req-456"
CONTROL = life.CONTROL_PATH


def content(entries):
    data = json.dumps({"schema_version": life.CONTROL_SCHEMA, "requests": entries}).encode()
    return {"type": "file", "encoding": "base64", "size": len(data),
            "content": base64.b64encode(data).decode()}


def fake_api(entries, *, historical=None, issue_state="open"):
    def api(path):
        if path.startswith("issues/") and path.split("/")[-1].isdigit():
            return {"number": int(path.split("/")[1]), "state": issue_state,
                    "labels": [{"name": "lf-request-blocked"}]}
        if path == f"contents/{CONTROL}?ref=main":
            return content(entries)
        if path == f"contents/{CONTROL}?ref={MERGE}":
            return content(entries if historical is None else historical)
        if path == "pulls/77":
            return {"number": 77, "merged": True, "merge_commit_sha": MERGE,
                    "base": {"ref": "main", "repo": {"full_name": "example/sandbox"}},
                    "head": {"repo": {"full_name": "example/sandbox"}}}
        if path == "issues/77/events?per_page=100&page=1":
            return [{"event": "labeled", "actor": {"login": "example"}, "label": {"name": "ready-to-merge"}}]
        raise AssertionError(path)
    return api


