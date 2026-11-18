#!/usr/bin/env python3
"""T46: fetch the project's audit skill at its pinned commit and verify it.

The skill is used from its owner's repository (never copied into this repo).
Every file under the skill path must match the per-file SHA-256 manifest, and
no file may be missing or extra; otherwise AUDIT_SKILL_PIN_MISMATCH.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_config import AuditConfigError, ROOT, load, manifest  # noqa: E402


class SkillPinError(ValueError):
    pass


def verify_tree(skill_dir: Path, files: dict) -> None:
    found = {}
    for path in sorted(skill_dir.rglob("*")):
        if path.is_symlink():
            raise SkillPinError("AUDIT_SKILL_PIN_MISMATCH:SYMLINK:" + path.relative_to(skill_dir).as_posix())
        if path.is_file() and "__pycache__" not in path.parts:
            found[path.relative_to(skill_dir).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    missing = sorted(set(files) - set(found))
    extra = sorted(set(found) - set(files))
    changed = sorted(k for k in set(files) & set(found) if files[k] != found[k])
    if missing or extra or changed:
        detail = (["missing=" + m for m in missing[:3]] + ["extra=" + e for e in extra[:3]]
                  + ["changed=" + c for c in changed[:3]])
        raise SkillPinError("AUDIT_SKILL_PIN_MISMATCH:" + ",".join(detail))


def fetch(config: dict, dest: Path, root: Path = ROOT, source_url: str | None = None) -> Path:
    """Checkout <repository>@<commit> into dest (depth 1) and verify the skill path."""
    skill = config["audit"]["skill"]
    files = manifest(config, root)
    url = source_url or f"https://github.com/{skill['repository']}"
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    git = ["git", "-C", str(dest)]
    try:
        subprocess.run(git + ["init", "-q"], check=True, capture_output=True)
        subprocess.run(git + ["fetch", "-q", "--depth", "1", url, skill["commit"]],
                       check=True, capture_output=True, timeout=600)
        subprocess.run(git + ["-c", "advice.detachedHead=false", "checkout", "-q",
                              skill["commit"], "--", skill["path"]],
                       check=True, capture_output=True)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        raise SkillPinError("AUDIT_SKILL_UNREACHABLE") from None
    skill_dir = dest / skill["path"]
    if not skill_dir.is_dir():
        raise SkillPinError("AUDIT_SKILL_UNREACHABLE")
    verify_tree(skill_dir, files)
    return skill_dir


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--dest", type=Path, required=True)
    a = ap.parse_args()
    try:
        skill_dir = fetch(load(a.project), a.dest)
    except (AuditConfigError, SkillPinError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}))
        return 1
    print(json.dumps({"status": "SKILL_VERIFIED", "skill_dir": str(skill_dir)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
