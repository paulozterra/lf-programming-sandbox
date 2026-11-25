"""R1: locate a request whose T7 delivery was cancelled before admission.

Called only by the scheduled, globally serialized T7 workflow. No user prompt,
model invocation or direct merge. Source is trusted main and verified GitHub
request/Train provenance; never inspect proposal code as instructions.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from pilot.config.project_config import storage_path
from pilot.orchestrator.request_lifecycle import request_state, OPEN
from pilot.orchestrator import chain_lots
from pilot.auto_integrate import original_request_merge

ROOT = Path(__file__).resolve().parents[2]
REQUEST = re.compile(r"req-[1-9][0-9]*\Z")
SHA = re.compile(r"[0-9a-f]{40}\Z")


def _t7_history() -> list[dict]:
    rows = []
    for page in range(1, 11):
        obj = chain_lots.api(f"actions/workflows/t7-request.yml/runs?per_page=100&page={page}")
        chunk, total = obj.get("workflow_runs"), obj.get("total_count")
        if (not isinstance(chunk, list) or type(total) is not int
                or total < 0 or total > 1000
                or len(chunk) != min(100, max(0, total - len(rows)))
                or any(not isinstance(x, dict) for x in chunk)):
            raise ValueError("R1_T7_HISTORY_INCOMPLETE")
        rows.extend(chunk)
        if len(rows) == total:
            break
    else:
        raise ValueError("R1_T7_HISTORY_INCOMPLETE")
    if len({r.get("id") for r in rows}) != len(rows):
        raise ValueError("R1_T7_HISTORY_INCOMPLETE")
    return rows


MAX_T7_FAILURES = 3
ROUTE_PATHS = ("pilot", "analysis")


def latest(rows: list[dict]) -> dict:
    return max(rows, key=lambda r: (str(r.get("created_at") or ""), int(r.get("id") or 0)))


def route_changed_since(root: Path, run: dict) -> bool:
    """True if trusted main changed route code after the commit a run used."""
    import subprocess
    sha = run.get("head_sha")
    if not isinstance(sha, str) or not SHA.fullmatch(sha):
        return False
    try:
        ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", sha, "HEAD"],
                                  cwd=root, capture_output=True, timeout=60).returncode == 0
        if not ancestor:
            return False
        changed = subprocess.run(["git", "diff", "--name-only", sha, "HEAD", "--", *ROUTE_PATHS],
                                 cwd=root, capture_output=True, text=True, timeout=60, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    # Request artifacts, exams and native task records are data, not route code.
    data = ("pilot/runs/", "pilot/holdouts/", "pilot/worker_v08/native_tasks/",
            "pilot/native_proposals/")
    return any(line and not line.startswith(data) for line in changed.splitlines())


def select(*, root: Path = ROOT) -> str | None:
    request_root = storage_path("requests_root", root=root)
    if not request_root.is_dir():
        return None
    runs = _t7_history()
    prs = chain_lots.api_list("pulls?state=open")
    if not isinstance(prs, list):
        raise ValueError("R1_T7_PRS_INCOMPLETE")
    for request_file in sorted(request_root.glob("req-*/request.md")):
        folder = request_file.parent
        request = folder.name
        if (not REQUEST.fullmatch(request) or folder.is_symlink()
                or request_file.is_symlink()):
            raise ValueError("R1_T7_REQUEST_PATH_INVALID")
        if (folder / "analysis.json").exists() or (folder / "state.json").exists():
            continue
        if request_state(request, chain_lots.api, root=root) != OPEN:
            continue
        metadata = folder / "request_meta.json"
        if metadata.is_symlink() or not metadata.is_file():
            raise ValueError("R1_T7_REQUEST_META_MISSING")
        info = json.loads(metadata.read_text(encoding="utf-8"))
        if info.get("issue") != int(request[4:]):
            raise ValueError("R1_T7_REQUEST_META_INVALID")
        source = original_request_merge(request, root)
        if not isinstance(source, str) or not SHA.fullmatch(source):
            raise ValueError("R1_T7_SOURCE_UNTRUSTED")
        # A candidate PR is already durable work; do not regenerate it.
        pending = False
        for pr in prs:
            if (not isinstance(pr, dict) or type(pr.get("number")) is not int
                    or not str((pr.get("head") or {}).get("ref") or "").startswith(
                        "lf/generated-t7/")):
                continue
            changes = chain_lots.api_list(f"pulls/{pr['number']}/files")
            if any(str(row.get("filename") or "").startswith(
                   f"{request_file.parent.relative_to(root).as_posix()}/")
                   for row in changes if isinstance(row, dict)):
                pending = True
                break
        if pending:
            continue
        matches = [row for row in runs if
                   (row.get("display_title") in ("T7 " + request, "T7 " + source)
                    or (row.get("head_sha") == source and
                        row.get("event") == "push"))]
        failures = [row for row in matches if row.get("status") == "completed"
                    and row.get("conclusion") == "failure"]
        # A failed T7 is retried only when trusted main changed the route's own
        # code after the latest failure (the defect may be fixed), and never
        # more than MAX_T7_FAILURES times. Unchanged route: stays stopped.
        retry = (bool(failures) and len(failures) < MAX_T7_FAILURES
                 and not any(row.get("status") == "completed" and row.get("conclusion") == "success"
                             for row in matches)
                 and route_changed_since(root, latest(failures)))
        for row in matches:
            if retry and row.get("status") == "completed" and row.get("conclusion") == "failure":
                continue
            if row.get("status") in ("queued", "in_progress", "waiting", "pending"):
                pending = True
                break
            if (row.get("status") == "completed"
                    and row.get("conclusion") in ("success", "failure")):
                # A successful T7 with no analysis merged is a governance
                # boundary, not permission to publish another candidate.
                pending = True
                break
            if (row.get("status") != "completed"
                    or row.get("conclusion") not in ("cancelled", "skipped")):
                raise ValueError("R1_T7_HISTORY_STATUS_UNKNOWN")
        if not pending:
            return request_file.relative_to(root).as_posix()
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    try:
        selected = select()
    except (ValueError, KeyError, OSError, chain_lots.ChainBlocked) as exc:
        raise SystemExit("R1_T7_SWEEP_BLOCKED:" + str(exc)) from exc
    args.out.write_text(selected + "\n" if selected else "", encoding="utf-8")
    print("R1_T7_RESUME_SELECTED" if selected else "R1_T7_NO_UNADMITTED_REQUEST")


if __name__ == "__main__":
    main()
