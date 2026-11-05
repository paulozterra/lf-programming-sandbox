from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

SKIP_SNAPSHOT_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "build",
    "dist",
}


def is_transient_directory_name(name: str) -> bool:
    return name in SKIP_SNAPSHOT_DIRS or name.endswith(".egg-info")


def is_transient_path(path: Path) -> bool:
    return any(is_transient_directory_name(part) for part in path.parts)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _reject_nonfinite_constant(value: str) -> Any:
    raise ValueError(f"non-finite JSON constant: {value}")


def strict_json_loads(text: str) -> Any:
    return json.loads(
        text,
        object_pairs_hook=_object_without_duplicate_keys,
        parse_constant=_reject_nonfinite_constant,
    )


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def evidence_envelope_payload(
    *,
    code: str,
    status: str,
    source_system: str,
    source_ref: str,
    head_sha: str,
    producer: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """Canonical preimage for an Evidence identity, excluding only its digest."""
    return {
        "code": code,
        "status": status,
        "source_system": source_system,
        "source_ref": source_ref,
        "head_sha": head_sha,
        "producer": producer,
        "metadata": metadata,
    }


def sha256_evidence_envelope(
    *,
    code: str,
    status: str,
    source_system: str,
    source_ref: str,
    head_sha: str,
    producer: str,
    metadata: dict[str, Any],
) -> str:
    return sha256_json(
        evidence_envelope_payload(
            code=code,
            status=status,
            source_system=source_system,
            source_ref=source_ref,
            head_sha=head_sha,
            producer=producer,
            metadata=metadata,
        )
    )


def source_snapshot_sha256(root: Path) -> str:
    """Hash the canonical local source tree by relative path and file bytes."""
    entries: list[dict[str, str]] = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if is_transient_path(rel):
            continue
        if path.is_symlink():
            raise ValueError(f"source snapshot does not accept symlink: {rel.as_posix()}")
        if not path.is_file():
            continue
        entries.append({"path": rel.as_posix(), "sha256": sha256_file(path)})
    return sha256_json(entries)
