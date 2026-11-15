#!/usr/bin/env python3
"""T17.2: classify post-CI policy C handoffs from policy C's live allowlist.

Runs in unprivileged CI. It only writes a boolean job output; the trusted
policy C workflow on main still authenticates every PR and check.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from pilot.auto_integrate import accepted_branch_kind


def should_notify(branch: str) -> bool:
    return accepted_branch_kind(branch) is not None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    branch = os.environ.get("POLICY_C_BRANCH", "")
    args.output.open("a", encoding="utf-8").write(
        "accepted=" + ("true" if should_notify(branch) else "false") + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
