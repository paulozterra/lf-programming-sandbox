#!/usr/bin/env python3
"""Trusted private-only age holdout gate. No oracle, key or stderr in logs."""
from __future__ import annotations
import argparse
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

TASK = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
RECIPIENT = re.compile(r"age1[023456789acdefghjklmnpqrstuvwxyz]{58}\Z")

class AgeBlocked(ValueError):
    pass

def holdout_ref(task: str, value: str) -> str:
    if not isinstance(task, str) or not TASK.fullmatch(task):
        raise AgeBlocked("NATIVE_TASK_ID_INVALID")
    expected = f"pilot/holdouts/{task}.oracle.json.age"
    if (not isinstance(value, str) or value != expected
            or PurePosixPath(value).is_absolute() or ".." in PurePosixPath(value).parts):
        raise AgeBlocked("HOLDOUT_REF_INVALID")
    return expected

def checked_ciphertext(root: Path, task: str, value: str) -> Path:
    rel = holdout_ref(task, value)
    directory = root / "pilot/holdouts"
    file = root / rel
    if directory.is_symlink() or file.is_symlink():
        raise AgeBlocked("HOLDOUT_REF_INVALID")
    if not file.is_file() or not file.resolve().is_relative_to(directory.resolve()):
        raise AgeBlocked("HOLDOUT_CIPHERTEXT_MISSING")
    return file

def validate_recipient(content: str) -> str:
    rows = [s.strip() for s in content.splitlines()
            if s.strip() and not s.lstrip().startswith("#")]
    if len(rows) != 1 or not RECIPIENT.fullmatch(rows[0]):
        raise AgeBlocked("HOLDOUT_RECIPIENT_INVALID")
    return rows[0]

def decrypt_private(root: Path, task: str, ref: str, sha: str,
                    identity_key: str, private: Path, age_bin: str = "age") -> Path:
    if not isinstance(sha, str) or not SHA256.fullmatch(sha):
        raise AgeBlocked("HOLDOUT_SHA_INVALID")
    source = checked_ciphertext(root, task, ref)
    if not isinstance(identity_key, str) or not identity_key.startswith("AGE-SECRET-KEY-1"):
        raise AgeBlocked("HOLDOUT_AGE_KEY_MISSING")
    private.mkdir(parents=True, exist_ok=True, mode=0o700)
    private.chmod(0o700)
    identity = private / ".age-identity"
    dest = private / "holdout.oracle.json"
    if identity.exists() or identity.is_symlink() or dest.exists() or dest.is_symlink():
        raise AgeBlocked("HOLDOUT_PRIVATE_PATH_EXISTS")
    try:
        fd = os.open(identity, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "wb") as out:
            out.write((identity_key.rstrip("\n") + "\n").encode("utf-8"))
        try:
            result = subprocess.run(
                [age_bin, "--decrypt", "--identity", str(identity),
                 "--output", str(dest), str(source)],
                capture_output=True, timeout=60, check=False)
        except (OSError, subprocess.TimeoutExpired):
            raise AgeBlocked("HOLDOUT_DECRYPT_FAILED") from None
        if result.returncode or not dest.is_file() or dest.is_symlink():
            raise AgeBlocked("HOLDOUT_DECRYPT_FAILED")
        dest.chmod(0o600)
        if hashlib.sha256(dest.read_bytes()).hexdigest() != sha:
            raise AgeBlocked("NATIVE_HOLDOUT_SHA_DRIFT")
        return dest
    except BaseException:
        if dest.is_file() and not dest.is_symlink():
            dest.unlink()
        raise
    finally:
        if identity.is_file() and not identity.is_symlink():
            identity.unlink()

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--validate-recipient", type=Path)
    p.add_argument("--control", type=Path)
    p.add_argument("--task")
    p.add_argument("--ref")
    p.add_argument("--expected-sha")
    p.add_argument("--private", type=Path)
    p.add_argument("--age-bin", default="age")
    a = p.parse_args()
    try:
        if a.validate_recipient is not None:
            validate_recipient(a.validate_recipient.read_text("utf-8"))
        else:
            decrypt_private(a.control, a.task, a.ref, a.expected_sha,
                            os.environ.get("PILOT_HOLDOUT_AGE_KEY", ""),
                            a.private, a.age_bin)
        return 0
    except (AgeBlocked, OSError, UnicodeError, ValueError):
        print("HOLDOUT_AGE_BLOCKED", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
