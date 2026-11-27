"""Central, fail-closed lifecycle decision for request-bound automation.

Synthetic or legacy identifiers must be deliberately enrolled in a versioned
allowlist. Closed GitHub issues are never active, independently of state_reason.
"""
from __future__ import annotations

# Resolve the trusted repository package for direct script execution.
import sys as _project_sys
from pathlib import Path as _project_Path
_project_sys.path.insert(0, str(_project_Path(__file__).resolve().parents[2]))

import base64
import json
from pathlib import Path
import re

from pilot.orchestrator.request_finalize import verified_chain_complete
from pilot.config.project_config import ProjectConfigError, storage, storage_path, template_path_pattern, repo_storage

ROOT = Path(__file__).resolve().parents[2]
REQUEST = re.compile(r"req-([1-9][0-9]*)\Z")
ALLOWLIST = ROOT / "pilot/orchestrator/request_lifecycle_allowlist.json"
OPEN = "OPEN"
SUSPENDING = "SUSPENDING"
SUSPENDED = "SUSPENDED"
CONTROL_PATH = "pilot/orchestrator/request_lifecycle_control.json"
CONTROL_SCHEMA = "LF_REQUEST_LIFECYCLE_CONTROL_V1"
CONTROL_STATES = {SUSPENDING, SUSPENDED, "ACTIVE"}
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
CLOSED_FINALIZED = "CLOSED_FINALIZED"
CLOSED_CANCELLED = "CLOSED_CANCELLED"
CODE = "REQUEST_STATE_UNRESOLVED"


class RequestStateError(ValueError):
    """Machine-readable state failure; must not authorize side effects."""


def unresolved():
    raise RequestStateError(CODE)


def _synthetic_allowed(request: str, allowlist: Path) -> bool:
    try:
        if allowlist.is_symlink() or not allowlist.is_file():
            unresolved()
        data = json.loads(allowlist.read_text(encoding="utf-8"))
        values = data["allowed_non_issue_requests"]
        if (not isinstance(values, list) or len(values) != len(set(values))
                or not all(isinstance(v, str) and re.fullmatch(
                    r"[a-z][a-z0-9_-]{0,63}", v) and not REQUEST.fullmatch(v)
                    for v in values)):
            unresolved()
        return request in values
    except (OSError, ValueError, TypeError, KeyError):
        unresolved()


def _finalized(request: str, root: Path) -> bool:
    """Use the canonical finalization proof, never a second implementation."""
    folder = storage_path("requests_root", request, root=root)
    return verified_chain_complete(folder, root=root)



def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            unresolved()
        result[key] = value
    return result


def parse_control(raw: bytes) -> dict:
    """Strict, versioned authorization ledger. No implicit reset by deletion."""
    try:
        if not isinstance(raw, bytes) or not 0 < len(raw) <= 65536:
            unresolved()
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_strict_object)
        if (not isinstance(value, dict) or set(value) != {"schema_version", "requests"}
                or value["schema_version"] != CONTROL_SCHEMA
                or not isinstance(value["requests"], dict)):
            unresolved()
        for slug, entry in value["requests"].items():
            if (not REQUEST.fullmatch(slug) or not isinstance(entry, dict)
                    or set(entry) != {"state", "authorization_pr"}
                    or entry["state"] not in CONTROL_STATES
                    or type(entry["authorization_pr"]) is not int
                    or entry["authorization_pr"] <= 0):
                unresolved()
        return value["requests"]
    except (ValueError, TypeError, KeyError, UnicodeError):
        unresolved()


def read_control(api, revision="main") -> dict:
    """Read current trusted main via GitHub, not a possibly stale job checkout."""
    if revision != "main" and (not isinstance(revision, str) or not SHA40.fullmatch(revision)):
        unresolved()
    try:
        item = api(f"contents/{CONTROL_PATH}?ref={revision}")
        if (not isinstance(item, dict) or item.get("type") != "file"
                or item.get("encoding") != "base64"
                or type(item.get("size")) is not int or not 0 < item["size"] <= 65536
                or not isinstance(item.get("content"), str)):
            unresolved()
        raw = base64.b64decode("".join(item["content"].splitlines()), validate=True)
        if len(raw) != item["size"]:
            unresolved()
        return parse_control(raw)
    except Exception as exc:
        raise RequestStateError(CODE) from exc


def control_state(request: str, api) -> str:
    """An enrolled request needs a real merged PR and an exact historical entry."""
    entries = read_control(api)
    entry = entries.get(request)
    if entry is None:
        return OPEN
    try:
        number = entry["authorization_pr"]
        pr = api(f"pulls/{number}")
        merge = pr.get("merge_commit_sha")
        base, head = pr.get("base", {}), pr.get("head", {})
        repo = base.get("repo", {}).get("full_name")
        if (pr.get("number") != number or pr.get("merged") is not True
                or base.get("ref") != "main" or not repo
                or head.get("repo", {}).get("full_name") != repo
                or not isinstance(merge, str) or not SHA40.fullmatch(merge)):
            unresolved()
        if read_control(api, merge).get(request) != entry:
            unresolved()
        relation = api(f"compare/{merge}...main")
        if (not isinstance(relation, dict)
                or relation.get("status") not in ("ahead", "identical")
                or relation.get("behind_by") != 0):
            unresolved()
        return OPEN if entry["state"] == "ACTIVE" else entry["state"]
    except Exception as exc:
        raise RequestStateError(CODE) from exc


def validate_control_transition(previous: dict, current: dict, number: int) -> str:
    """The Train must use this before integrating any subsequent policy PR.
    SUSPENDING denies admission while old jobs drain; only then may the owner
    authorize SUSPENDED. ACTIVE is explicit and never implied by deletion.
    """
    if (type(number) is not int or number <= 0
            or any(slug not in current for slug in previous)):
        unresolved()
    changed = [slug for slug, entry in current.items() if previous.get(slug) != entry]
    if len(changed) != 1:
        unresolved()
    slug = changed[0]
    old = previous.get(slug, {}).get("state", "ACTIVE")
    new = current[slug]
    permitted = {"ACTIVE": SUSPENDING, SUSPENDING: SUSPENDED, SUSPENDED: "ACTIVE"}
    if new["state"] != permitted.get(old) or new["authorization_pr"] != number:
        unresolved()
    return slug


def inactive_reason(state: str) -> str:
    if state in (SUSPENDING, SUSPENDED):
        return "REQUEST_SUSPENDED"
    if state in (CLOSED_FINALIZED, CLOSED_CANCELLED):
        return "REQUEST_CLOSED"
    unresolved()


def request_state(request: str, api, *, root: Path = ROOT,
                  allowlist: Path | None = None) -> str:
    """Freshly resolve a GitHub issue before each external effect boundary."""
    if not isinstance(request, str):
        unresolved()
    match = REQUEST.fullmatch(request)
    if match is None:
        if _synthetic_allowed(request, allowlist or ALLOWLIST):
            return OPEN
        unresolved()
    number = int(match.group(1))
    try:
        item = api("issues/" + str(number))
    except Exception as exc:
        raise RequestStateError(CODE) from exc
    if (not isinstance(item, dict) or type(item.get("number")) is not int
            or item["number"] != number or item.get("pull_request")
            or item.get("state") not in ("open", "closed")):
        unresolved()
    if item["state"] == "open":
        return control_state(request, api)
    return CLOSED_FINALIZED if _finalized(request, root) else CLOSED_CANCELLED


def require_open(request: str, api, *, root: Path = ROOT) -> None:
    state = request_state(request, api, root=root)
    if state != OPEN:
        raise RequestStateError(inactive_reason(state))


def request_for_task(task: str, *, root: Path = ROOT) -> str:
    """Resolve a task against unique, trusted main chain plans; never proposal data.

    Both historical and per-request plans are supported. Duplicate copies for
    the same request must match byte-for-byte. Zero or multiple owners deny.
    """
    if not isinstance(task, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", task):
        unresolved()
    registration = storage_path("registrations_root", task + ".json", root=root)
    if registration.is_symlink() or not registration.is_file():
        unresolved()
    sources: dict[str, Path] = {}
    try:
        folders = [
            (p.stem, p) for p in sorted((storage_path("chain_plans_root", root=root)).glob("*.json"))
        ] + [
            (p.parent.name, p) for p in sorted((storage_path("requests_root", root=root)).glob("*/chain_plan.json"))
        ]
        for request, path in folders:
            if (path.is_symlink() or path.parent.is_symlink()
                    or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", request)):
                unresolved()
            if request in sources:
                if sources[request].read_bytes() != path.read_bytes():
                    unresolved()
                continue
            sources[request] = path
        owners = []
        for request, path in sources.items():
            obj = json.loads(path.read_text(encoding="utf-8"))
            bindings = obj["bindings"]
            if (not isinstance(obj, dict) or obj.get("request_id") != request
                    or not isinstance(bindings, list)):
                unresolved()
            hits = [entry for entry in bindings if isinstance(entry, dict)
                    and entry.get("task_name") == task]
            if len(hits) > 1:
                unresolved()
            if hits:
                entry = hits[0]
                if (not isinstance(entry.get("lot_id"), str)
                        or not isinstance(entry.get("template_path"), str)
                        or not entry["template_path"].startswith(repo_storage()["requests_root"] + "/" + request + "/")):
                    unresolved()
                owners.append(request)
        if len(owners) != 1:
            unresolved()
        return owners[0]
    except ProjectConfigError:
        raise
    except (OSError, ValueError, TypeError, KeyError, UnicodeError) as exc:
        raise RequestStateError(CODE) from exc


def github_issue_api(path: str) -> dict:
    """Read GitHub state with the trusted job token, never an input-provided token."""
    import os
    import subprocess
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo or not re.fullmatch(r"[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+", repo):
        unresolved()
    result = subprocess.run(
        ["gh", "api", "repos/" + repo + "/" + path],
        env={**os.environ, "GH_TOKEN": token},
        capture_output=True, text=True, timeout=30, check=True)
    response = json.loads(result.stdout)
    if not isinstance(response, dict):
        unresolved()
    return response


def require_task_open(task: str, *, root: Path = ROOT, api=None) -> str:
    """Typed fail-closed gate shared by Worker and CP3.5."""
    request = request_for_task(task, root=root)
    require_open(request, api or github_issue_api, root=root)
    return request
