"""Central, fail-closed lifecycle decision for request-bound automation.

Synthetic or legacy identifiers must be deliberately enrolled in a versioned
allowlist. Closed GitHub issues are never active, independently of state_reason.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

from pilot.orchestrator.request_finalize import verified_chain_complete
from pilot.config.project_config import ProjectConfigError, storage, storage_path, template_path_pattern

ROOT = Path(__file__).resolve().parents[2]
REQUEST = re.compile(r"req-([1-9][0-9]*)\Z")
ALLOWLIST = ROOT / "pilot/orchestrator/request_lifecycle_allowlist.json"
OPEN = "OPEN"
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
        return OPEN
    return CLOSED_FINALIZED if _finalized(request, root) else CLOSED_CANCELLED


def require_open(request: str, api, *, root: Path = ROOT) -> None:
    if request_state(request, api, root=root) != OPEN:
        raise RequestStateError("REQUEST_CLOSED")


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
                        or not entry["template_path"].startswith(storage(root=root)["requests_root"] + "/" + request + "/")):
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
