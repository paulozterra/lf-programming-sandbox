"""Central, fail-closed lifecycle decision for request-bound automation.

Synthetic or legacy identifiers must be deliberately enrolled in a versioned
allowlist. Closed GitHub issues are never active, independently of state_reason.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

from pilot.orchestrator.request_finalize import verified_chain_complete

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
    folder = root / "pilot/runs" / request
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
