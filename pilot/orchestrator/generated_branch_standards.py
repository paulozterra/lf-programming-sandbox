#!/usr/bin/env python3
"""T17: exact standards check for generated branches, with official renderer.

No custom CAMBIOS renderer and no remote mutation. The actual diff against
the originating main commit is the sole authority for affected.paths.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess

CHANGE = re.compile(r"standards/changes/CHG-[0-9]{4}[.]json\Z")
KINDS = frozenset({"registration", "integration", "registry", "generated-t7", "request"})


class BranchStandardsError(ValueError):
    pass


def command(root: Path, argv: list[str]) -> bytes:
    p = subprocess.run(argv, cwd=root, capture_output=True, timeout=90)
    if p.returncode:
        raise BranchStandardsError("OFFICIAL_OR_GIT_COMMAND_FAILED")
    return p.stdout


def changed_paths(root: Path, base: str) -> list[str]:
    raw = command(root, ["git", "diff", "--name-only", "-z", base, "--"])
    try:
        result = [p.decode("utf-8") for p in raw.split(b"\0") if p]
    except UnicodeError as exc:
        raise BranchStandardsError("INVALID_DIFF_PATH") from exc
    if len(result) != len(set(result)):
        raise BranchStandardsError("INVALID_DIFF_PATH")
    return sorted(result)


def official(root: Path, *args: str):
    command(root, ["python3", "standards/tools/changes.py", *args])


def synchronize(root: Path, kind: str, *,
                base: str = "origin/main", chg_file: str | None = None) -> list[str]:
    if kind not in KINDS:
        raise BranchStandardsError("INVALID_BRANCH_KIND")
    root = root.resolve()
    if chg_file is None:
        # A generated branch may acquire a CHG in a later route revision.
        # Detect it from the actual staged/tracked Git diff, not its branch name.
        candidates = [p for p in changed_paths(root, base) if CHANGE.fullmatch(p)]
        if len(candidates) > 1:
            raise BranchStandardsError("AMBIGUOUS_GENERATED_CHANGE")
        chg_file = candidates[0] if candidates else None
    if chg_file is not None:
        if not CHANGE.fullmatch(chg_file) or not (root / chg_file).is_file():
            raise BranchStandardsError("INVALID_CHANGE_PATH")
        command(root, ["git", "add", "--", chg_file])
        official(root, "render")
        command(root, ["git", "add", "--", "standards/CAMBIOS.md"])
        paths = changed_paths(root, base)
        if chg_file not in paths or "standards/CAMBIOS.md" not in paths:
            raise BranchStandardsError("CHANGE_NOT_IN_DIFF")
        document = json.loads((root / chg_file).read_text("utf-8"))
        if document.get("change_id") != Path(chg_file).stem:
            raise BranchStandardsError("CHANGE_ID_MISMATCH")
        document["affected"]["paths"] = paths
        (root / chg_file).write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n", "utf-8")
        command(root, ["git", "add", "--", chg_file])
        # Render again after CHG rewrite (and after later PR URL updates).
        official(root, "render")
        command(root, ["git", "add", "--", "standards/CAMBIOS.md"])
    official(root, "render", "--check")
    official(root, "validate")
    paths = changed_paths(root, base)
    if chg_file is not None:
        if json.loads((root / chg_file).read_text("utf-8"))["affected"]["paths"] != paths:
            raise BranchStandardsError("CHANGE_DIFF_DRIFT")
    return paths


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", choices=sorted(KINDS), required=True)
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--chg")
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    try:
        paths = synchronize(args.root, args.kind, base=args.base, chg_file=args.chg)
    except (BranchStandardsError, KeyError, TypeError, OSError,
            ValueError, subprocess.TimeoutExpired):
        raise SystemExit("GENERATED_BRANCH_STANDARDS_INVALID:" + args.kind)
    print(json.dumps({"kind": args.kind, "paths": paths}, sort_keys=True))


if __name__ == "__main__":
    main()
