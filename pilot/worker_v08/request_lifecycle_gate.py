#!/usr/bin/env python3
"""Trusted Worker lifecycle gate before untrusted proposal acceptance executes.

This entrypoint is run from the pinned control checkout in its own GitHub
Actions step. No token or state-fetch logic may run in the Worker step.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pilot.orchestrator.request_lifecycle import RequestStateError, require_task_open


def recheck(control: Path, task: str, *, checker=None) -> str:
    """Reject unknown/closed tasks before any attempt proof or model invocation."""
    return (checker or require_task_open)(task, root=control)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--task", required=True)
    args = parser.parse_args()
    try:
        recheck(args.control, args.task)
    except RequestStateError as exc:
        # Never include any untrusted issue response or token in a job log.
        reason = str(exc)
        print(reason if reason in ("REQUEST_CLOSED", "REQUEST_SUSPENDED")
              else "REQUEST_STATE_UNRESOLVED", file=sys.stderr)
        return 1
    except Exception:
        print("REQUEST_STATE_UNRESOLVED", file=sys.stderr)
        return 1
    print("REQUEST_OPEN_VERIFIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
