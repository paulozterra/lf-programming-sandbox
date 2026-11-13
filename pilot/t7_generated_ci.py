#!/usr/bin/env python3
"""T7 CI check for bot-generated evidence, executed from trusted main only.

The caller must check out main, never PR head. No model and no hidden exams.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

from auto_integrate import (
    BOT, GitHub, PolicyBlocked, eligible_pr, pr_files, verify_generated_content
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--branch", required=True)
    parser.add_argument("--sha", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    try:
        local = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                               capture_output=True, text=True, check=True).stdout.strip()
        remote = subprocess.run(["git", "rev-parse", "origin/main"], cwd=root,
                                capture_output=True, text=True, check=True).stdout.strip()
        if local != remote or os.environ.get("GITHUB_REPOSITORY") != (
                "paulozterra/lf-programming-sandbox"):
            raise PolicyBlocked("GENERATED_CONTENT_DRIFT")
        api = GitHub(os.environ.get("GH_TOKEN", ""))
        prs = api.pages("/pulls?state=open", None)
        matching = [row["number"] for row in prs
                    if row.get("head", {}).get("ref") == args.branch
                    and row.get("head", {}).get("sha") == args.sha
                    and row.get("user", {}).get("login") == BOT]
        if len(matching) != 1:
            raise PolicyBlocked("GENERATED_CONTENT_DRIFT")
        pr = api.request("GET", f"/pulls/{matching[0]}")
        paths = pr_files(api, matching[0])
        kind = eligible_pr(pr, paths)
        if kind not in ("generated-t7", "implemented-registry"):
            raise PolicyBlocked("GENERATED_CONTENT_DRIFT")
        verify_generated_content(api, pr, paths, kind)
    except (PolicyBlocked, OSError, ValueError, TypeError, KeyError,
            subprocess.SubprocessError) as exc:
        print("GENERATED_CONTENT_DRIFT:" + str(exc).split(":", 1)[0], file=sys.stderr)
        return 2
    print("T7_GENERATED_CONTENT_BYTE_EQUALITY_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
