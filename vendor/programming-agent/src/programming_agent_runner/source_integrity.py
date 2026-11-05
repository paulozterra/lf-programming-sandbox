from __future__ import annotations

import hashlib
import stat
from pathlib import Path
from typing import Any

from .hashutil import is_transient_path, sha256_json


def _git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    payload = f"blob {len(data)}\0".encode("ascii") + data
    return hashlib.sha1(payload, usedforsecurity=False).hexdigest()


def local_source_tree(root: Path) -> dict[str, Any]:
    """Return a deterministic Git-compatible manifest for the bytes being audited."""
    entries: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if is_transient_path(rel):
            continue
        if path.is_symlink():
            raise ValueError(f"source tree does not accept symlink: {rel.as_posix()}")
        if not path.is_file():
            continue
        mode = "100755" if path.stat().st_mode & stat.S_IXUSR else "100644"
        entries.append(
            {
                "path": rel.as_posix(),
                "mode": mode,
                "type": "blob",
                "sha": _git_blob_sha(path),
            }
        )
    return {
        "total_count": len(entries),
        "manifest_sha256": sha256_json(entries),
        "entries": entries,
    }


def _entry_map(entries: Any) -> dict[str, tuple[str, str, str]] | None:
    if not isinstance(entries, list):
        return None
    result: dict[str, tuple[str, str, str]] = {}
    for item in entries:
        if not isinstance(item, dict):
            return None
        path = item.get("path")
        mode = item.get("mode")
        type_ = item.get("type")
        sha = item.get("sha")
        if not isinstance(path, str) or not path:
            return None
        if not isinstance(mode, str) or not mode:
            return None
        if not isinstance(type_, str) or not type_:
            return None
        if not isinstance(sha, str) or not sha:
            return None
        if path in result:
            return None
        result[path] = (mode, type_, sha)
    return result


def reconcile_source_tree(local: dict[str, Any], remote: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    details: dict[str, Any] = {
        "local_manifest_sha256": local.get("manifest_sha256"),
        "remote_tree_sha": remote.get("tree_sha"),
        "local_count": local.get("total_count"),
        "remote_count": remote.get("total_count"),
        "missing_local": [],
        "unexpected_local": [],
        "mismatched": [],
    }
    if remote.get("truncated") is not False:
        details["reason"] = "REMOTE_TREE_TRUNCATED_OR_UNKNOWN"
        return "BLOCKED", details
    local_map = _entry_map(local.get("entries"))
    remote_map = _entry_map(remote.get("entries"))
    if local_map is None or remote_map is None:
        details["reason"] = "SOURCE_TREE_PAYLOAD_INVALID"
        return "BLOCKED", details

    details["missing_local"] = sorted(set(remote_map) - set(local_map))
    details["unexpected_local"] = sorted(set(local_map) - set(remote_map))
    details["mismatched"] = [
        {"path": path, "local": local_map[path], "remote": remote_map[path]}
        for path in sorted(set(local_map) & set(remote_map))
        if local_map[path] != remote_map[path]
    ]
    if details["missing_local"] or details["unexpected_local"] or details["mismatched"]:
        details["reason"] = "SOURCE_TREE_MISMATCH"
        return "FAIL", details
    details["reason"] = "SOURCE_TREE_MATCH"
    return "PASS", details
