"""Central, fail-closed lifecycle decision for request-bound automation.

Synthetic or legacy identifiers must be deliberately enrolled in a versioned
allowlist. Closed GitHub issues are never active, independently of state_reason.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

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
    """Same proof contract as request_finalize: final H_REPORT and every lot integrated."""
    folder = root / "pilot/runs" / request
    paths = [folder / "lots.json", folder / "H_REPORT.md",
             root / "pilot/registry/implemented.json"]
    if any(p.is_symlink() or not p.is_file() for p in paths):
        return False
    try:
        lots = json.loads(paths[0].read_text(encoding="utf-8"))["lots"]
        ledger = json.loads(paths[2].read_text(encoding="utf-8"))["entries"]
        if not isinstance(lots, list) or not lots or not isinstance(ledger, list):
            return False
        planned = {x.get("id", x.get("lot_id")) for x in lots if isinstance(x, dict)}
        if len(planned) != len(lots) or not all(
                isinstance(i, str) and i for i in planned):
            return False
        merged = {x.get("lot") for x in ledger if isinstance(x, dict)
                  and x.get("request") == request
                  and x.get("merge_sha")
                  and x.get("status") in ("ATTESTED", "NO_DERIVABLE")}
        return planned.issubset(merged)
    except (OSError, ValueError, KeyError, TypeError, UnicodeError):
        return False


def request_state(request: str, api, *, root: Path = ROOT,
                  allowlist: Path | None = None) -> str:
    """Freshly resolve a GitHub issue before each external effect boundary."""
    if not isinstance(request, str):
        unresolved()
    match = REQUEST.fullmatch(request)
    if match is None:
        if _synthetic_allowed(request, allowlist or root /
                              "pilot/orchestrator/request_lifecycle_allowlist.json"):
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
