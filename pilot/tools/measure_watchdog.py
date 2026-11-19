#!/usr/bin/env python3
"""T52: measure T9.1 watchdog activations in a time window (read-only).

Lists watchdog runs with `gh api` (created=START..END), counts them by event
and conclusion, and reads the source run id from the run title
("T9.1 watchdog <event> source=<id|sweep>", T52) to tell how many source runs
arrived by workflow_run, by dispatch, or by both.

A listing that cannot be proven complete is reported as INCOMPLETE, never as
zero activations.

    python3 pilot/tools/measure_watchdog.py \
        --start 2026-11-19T05:41:48Z --end 2026-11-19T05:56:48Z
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import json
import re
import subprocess
import sys

REPO = "paulozterra/lf-programming-sandbox"
WORKFLOW = "request-failure-watchdog.yml"
MAX_PAGES = 10
SOURCE = re.compile(r"\bsource=([1-9][0-9]*|sweep)\b")


def parse_time(value: str) -> datetime:
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("TIME_WITHOUT_ZONE")
    return stamp


def gh_page(endpoint: str) -> dict:
    out = subprocess.run(["gh", "api", endpoint], check=True, text=True,
                         capture_output=True, timeout=60).stdout
    return json.loads(out)


def fetch(start: str, end: str, page_fn=gh_page, repo: str = REPO,
          workflow: str = WORKFLOW, max_pages: int = MAX_PAGES) -> tuple[list[dict], bool]:
    """Return (runs, complete). complete=False if pagination cannot be proven."""
    runs: list[dict] = []
    seen: set[int] = set()
    total = None
    for page in range(1, max_pages + 1):
        data = page_fn(f"repos/{repo}/actions/workflows/{workflow}/runs"
                       f"?created={start}..{end}&per_page=100&page={page}")
        rows = data.get("workflow_runs") if isinstance(data, dict) else None
        count = data.get("total_count") if isinstance(data, dict) else None
        if not isinstance(rows, list) or type(count) is not int:
            return runs, False
        if total is None:
            total = count
        elif count != total:
            return runs, False  # the window changed while paging
        for row in rows:
            if not isinstance(row, dict) or type(row.get("id")) is not int:
                return runs, False
            if row["id"] in seen:
                return runs, False
            seen.add(row["id"])
            runs.append(row)
        if len(runs) >= total or not rows:
            return runs, len(runs) == total
    return runs, False


def summarize(runs: list[dict], start: str, end: str, complete: bool) -> dict:
    lo, hi = parse_time(start), parse_time(end)
    inside = []
    for row in runs:
        try:
            created = parse_time(str(row.get("created_at")))
        except ValueError:
            complete = False
            continue
        if lo <= created < hi:  # start inclusive, end exclusive
            inside.append(row)
    by_event = Counter(str(r.get("event")) for r in inside)
    by_conclusion = Counter(str(r.get("conclusion") or r.get("status")) for r in inside)
    arrivals: dict[str, set[str]] = {}
    untitled = 0
    for row in inside:
        match = SOURCE.search(str(row.get("display_title") or ""))
        if not match:
            untitled += 1  # runs from before T52 carry no source in the title
            continue
        if match.group(1) != "sweep":
            arrivals.setdefault(match.group(1), set()).add(str(row.get("event")))
    both = sum(1 for e in arrivals.values()
               if {"workflow_run", "workflow_dispatch"} <= e)
    only_run = sum(1 for e in arrivals.values() if e == {"workflow_run"})
    only_dispatch = sum(1 for e in arrivals.values() if e == {"workflow_dispatch"})
    return {
        "status": "COMPLETE" if complete else "INCOMPLETE",
        "window": {"start": start, "end": end},
        "total": len(inside),
        "by_event": dict(sorted(by_event.items())),
        "by_conclusion": dict(sorted(by_conclusion.items())),
        "sources": len(arrivals),
        "sources_both_paths": both,
        "sources_only_workflow_run": only_run,
        "sources_only_dispatch": only_dispatch,
        "both_ratio": round(both / len(arrivals), 3) if arrivals else None,
        "runs_without_source_title": untitled,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--repo", default=REPO)
    args = parser.parse_args(argv)
    if parse_time(args.start) >= parse_time(args.end):
        print(json.dumps({"status": "INVALID_WINDOW"}))
        return 2
    try:
        runs, complete = fetch(args.start, args.end, repo=args.repo)
    except (subprocess.SubprocessError, OSError, ValueError) as exc:
        print(json.dumps({"status": "INCOMPLETE", "error": type(exc).__name__}))
        return 1
    result = summarize(runs, args.start, args.end, complete)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if complete else 1


if __name__ == "__main__":
    sys.exit(main())
