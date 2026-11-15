"""T16: redaction-only Worker bridge for trusted LF rule examples.

The authoritative rules and assembled receipt remain unchanged. The vendored
secret scanner is the same safety gate used by the Worker; real credentials and
unrecognized patterns fail closed rather than being smuggled into context.
"""
from __future__ import annotations

from programming_agent_runner.worker_secrets import (
    _SECRET_PATTERNS, secret_text_reason,
)


class WorkerContextUnsafe(ValueError):
    pass


def safe_rule_context(source: bytes) -> tuple[bytes, int]:
    if not isinstance(source, bytes):
        raise WorkerContextUnsafe("LF_RULE_CONTEXT_INVALID")
    try:
        raw = source.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise WorkerContextUnsafe("LF_RULE_CONTEXT_INVALID") from exc
    risk = secret_text_reason(raw)
    if risk is None:
        return source, 0
    if risk != "ASSIGNMENT_SECRET":
        raise WorkerContextUnsafe("LF_RULE_CONTEXT_SECRET")
    # Reuse the exact version-pinned vendor pattern, never weaken its scanner.
    pattern = dict(_SECRET_PATTERNS)["ASSIGNMENT_SECRET"]

    def redact(match):
        item = match.group(0)
        separator = min((i for i, char in enumerate(item) if char in ":="),
                        default=-1)
        if separator < 0:
            raise WorkerContextUnsafe("LF_RULE_CONTEXT_SECRET")
        lead, value = item[:separator + 1], item[separator + 1:]
        spaces = value[:len(value) - len(value.lstrip())]
        stripped = value.lstrip()
        quote = stripped[0] if stripped[:1] in ("'", '"') else ""
        return lead + spaces + quote + "REDACTED"

    result, count = pattern.subn(redact, raw)
    if count == 0 or secret_text_reason(result) is not None:
        raise WorkerContextUnsafe("LF_RULE_CONTEXT_SECRET")
    return result.encode("utf-8"), count
