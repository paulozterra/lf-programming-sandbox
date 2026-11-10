"""Fail-closed push gate: proposal commit descends from trusted main, with one JSON change.

Reads only Git objects. Never executes content from the proposal commit.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

EXPECTED_PATH = "pilot/native_proposals/ex6.json"
_SHA40 = re.compile(r"[0-9a-f]{40}\Z")

class ProposalPushBlocked(ValueError):
    pass

def _git(repo: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.DEVNULL)

def validate_proposal_only(control: Path, proposal_sha: str, *, main_sha: str | None = None) -> dict:
    if _SHA40.fullmatch(proposal_sha) is None:
        raise ProposalPushBlocked("NATIVE_PUSH_SHA_INVALID")
    main_sha = main_sha or _git(control, "rev-parse", "HEAD").decode().strip()
    if not _SHA40.fullmatch(main_sha):
        raise ProposalPushBlocked("NATIVE_PUSH_MAIN_INVALID")
    if proposal_sha == main_sha:
        raise ProposalPushBlocked("NATIVE_PUSH_NO_PROPOSAL_DELTA")
    if subprocess.run(["git", "-C", str(control), "merge-base", "--is-ancestor",
                       main_sha, proposal_sha], check=False,
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode != 0:
        raise ProposalPushBlocked("NATIVE_PUSH_NOT_DESCENDANT_OF_TRUSTED_MAIN")
    raw = _git(control, "diff", "--name-status", "-z", "--no-renames",
               main_sha, proposal_sha)
    fields = raw.split(b"\x00")
    if len(fields) != 3 or fields[-1] != b"" or fields[0] not in (b"A", b"M") or fields[1] != EXPECTED_PATH.encode():
        raise ProposalPushBlocked("NATIVE_PUSH_SCOPE_INVALID")
    info = _git(control, "ls-tree", proposal_sha, "--", EXPECTED_PATH).decode().strip().split()
    if len(info) < 3 or info[0] != "100644" or info[1] != "blob":
        raise ProposalPushBlocked("NATIVE_PUSH_PROPOSAL_NOT_REGULAR_FILE")
    raw_json = _git(control, "show", proposal_sha + ":" + EXPECTED_PATH)
    if len(raw_json) > 200_000 or len(raw_json) == 0:
        raise ProposalPushBlocked("NATIVE_PUSH_PROPOSAL_SIZE_INVALID")
    try:
        obj = json.loads(raw_json)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ProposalPushBlocked("NATIVE_PUSH_JSON_INVALID") from exc
    if not isinstance(obj, dict):
        raise ProposalPushBlocked("NATIVE_PUSH_JSON_OBJECT_REQUIRED")
    return {"proposal_commit_sha": proposal_sha, "base_commit_sha": main_sha,
            "proposal_path": EXPECTED_PATH, "scope_valid": True}

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--control", required=True, type=Path)
    parser.add_argument("--sha", required=True)
    args = parser.parse_args()
    print(json.dumps(validate_proposal_only(args.control, args.sha), sort_keys=True))

if __name__ == "__main__":
    main()
