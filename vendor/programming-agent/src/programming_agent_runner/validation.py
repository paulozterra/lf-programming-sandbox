from __future__ import annotations

import re
from pathlib import Path

HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class InputValidationError(ValueError):
    pass


def validate_head_sha(value: str) -> None:
    if not HEX40.fullmatch(value):
        raise InputValidationError("head_sha must be a lowercase 40-hex Git SHA")


def validate_sha256(value: str) -> None:
    if not HEX64.fullmatch(value):
        raise InputValidationError("source_snapshot_sha256 must be a lowercase 64-hex SHA-256")


def validate_repo_full_name(value: str) -> None:
    if not REPO.fullmatch(value):
        raise InputValidationError("repo_full_name must be owner/repo")


def validate_repo_path(path: Path) -> None:
    if not path.exists() or not path.is_dir():
        raise InputValidationError("repo_path must exist and be a directory")
