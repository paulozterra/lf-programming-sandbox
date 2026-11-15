"""T12 issue de-duplication from source literal and catalog screen, no model."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import unicodedata

DUPLICATE = "lf-request-duplicate"
LABEL = "lf-request"


class DuplicateBlocked(ValueError):
    pass


def normalized(value: str) -> str:
    if not isinstance(value, str):
        raise DuplicateBlocked("PEDIDO_FORMULARIO_INVALIDO")
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def screen(root: Path, value: str) -> str:
    from analysis.host.request_catalog import resolve, CatalogueBlocked
    try:
        return resolve(root, value.encode("utf-8"))[0]
    except CatalogueBlocked:
        # Dedupe only when both requests have an unambiguous catalog identity.
        return ""


def candidate(api, issue: dict, text: str, *, root: Path) -> int | None:
    from pilot.orchestrator.issue_intake import request_text, metadata
    info = metadata(issue)
    created = datetime.fromisoformat(info["date"].replace("Z", "+00:00"))
    target = screen(root, text)
    if not target:
        return None
    signature = normalized(text)
    matches = []
    for page in range(1, 11):
        rows = api.call("GET", f"/issues?state=open&labels={LABEL}&per_page=100&page={page}")
        if not isinstance(rows, list):
            raise DuplicateBlocked("PEDIDO_DUPLICATE_LOOKUP_UNVERIFIED")
        for row in rows:
            if (not isinstance(row, dict)
                    or row.get("state") != "open"
                    or "pull_request" in row
                    or type(row.get("number")) is not int
                    or row["number"] >= info["issue"]
                    or not any(isinstance(x, dict) and x.get("name") == LABEL
                               for x in row.get("labels", []))
                    or any(isinstance(x, dict) and x.get("name") == DUPLICATE
                           for x in row.get("labels", []))):
                continue
            try:
                stamp = datetime.fromisoformat(row["created_at"].replace("Z","+00:00"))
                other = request_text(row["body"])
            except (KeyError, TypeError, ValueError):
                continue
            if (timedelta(0) <= created - stamp <= timedelta(hours=24)
                    and normalized(other) == signature and screen(root, other) == target):
                matches.append(row["number"])
        if len(rows) < 100:
            break
    else:
        raise DuplicateBlocked("PEDIDO_DUPLICATE_LOOKUP_UNBOUNDED")
    return min(matches) if matches else None


def mark(api, number: int, older: int):
    # The intake workflow serializes all issue decisions across this repo.
    labels = api.call("GET", "/labels?per_page=100")
    if not isinstance(labels, list) or len(labels) >= 100:
        raise DuplicateBlocked("PEDIDO_DUPLICATE_LABELS_UNVERIFIED")
    if not any(x.get("name") == DUPLICATE for x in labels if isinstance(x, dict)):
        api.call("POST", "/labels", {"name": DUPLICATE,
                                     "description": "Possible duplicate request; remove to force",
                                     "color": "C8CDD2"})
    api.call("POST", f"/issues/{number}/labels", {"labels": [DUPLICATE]})
    api.call("POST", f"/issues/{number}/comments",
             {"body": f"posible duplicado de #{older}"})
