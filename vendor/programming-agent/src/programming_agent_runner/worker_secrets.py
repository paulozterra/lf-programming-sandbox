from __future__ import annotations

import re
from pathlib import PurePosixPath

_SENSITIVE_NAMES = {
    ".env",
    ".npmrc",
    ".pypirc",
    "credentials",
    "credentials.json",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "id_rsa",
}
_SENSITIVE_SUFFIXES = (".key", ".p12", ".pfx", ".pem")
_SECRET_PATTERNS = (
    ("PRIVATE_KEY", re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE" r" KEY-----")),
    ("OPENAI_API_KEY", re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}\b")),
    ("GITHUB_TOKEN", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}\b")),
    ("AWS_ACCESS_KEY", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    (
        "ASSIGNMENT_SECRET",
        re.compile(
            r"(?i)\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)\b\s*[:=]\s*['\"]?[^\s'\"]{16,}"
        ),
    ),
)


def sensitive_path_reason(path: str) -> str | None:
    name = PurePosixPath(path).name.lower()
    if name in _SENSITIVE_NAMES or name.startswith(".env.") or name.endswith(_SENSITIVE_SUFFIXES):
        return "SENSITIVE_PATH"
    return None


def secret_text_reason(text: str) -> str | None:
    for reason, pattern in _SECRET_PATTERNS:
        if pattern.search(text):
            return reason
    return None
