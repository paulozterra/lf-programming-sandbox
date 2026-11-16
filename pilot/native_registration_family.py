"""Trusted LF native-registration branch subfamilies (T23.1).

A registration Task ID must never be inferred from an auxiliary bot branch.
This is the single classifier shared by lifecycle, Train handoff, Policy C,
conflict recovery and failure watchdog.
"""
from __future__ import annotations

import re

PREFIX = "lf/native-registration/"
TASK = r"[a-z][a-z0-9_-]{0,31}"
COMMIT = r"[0-9a-f]{12}"
# All auxiliary prefixes produced by CP3.6/T17/T18/T19/T23/T26.
# Match auxiliary families *before* task registration to prevent mistaken
# exam-request closures for names like route-python-req186contrato1.
AUXILIARY = ("route-python-", "pack-", "envelope-", "plan-")
VALID = re.compile(r"^" + re.escape(PREFIX) + r"(" + TASK + r")-(" + COMMIT + r")$")
AUX = {
    prefix: re.compile(r"^" + re.escape(PREFIX + prefix)
                       + r"(" + TASK + r")-(" + COMMIT + r")$")
    for prefix in AUXILIARY
}


def registration_family(branch: str) -> tuple[str, str | None]:
    """Return (registration|auxiliary|invalid, task or None).

    Every named auxiliary must have a valid task and 12-hex source SHA.
    Ambiguous or unrecognized registration branches are invalid, not exams.
    """
    if not isinstance(branch, str) or not branch.startswith(PREFIX):
        return "invalid", None
    for prefix, expression in AUX.items():
        match = expression.fullmatch(branch)
        if match:
            return "auxiliary", match.group(1)
        if branch[len(PREFIX):].startswith(prefix):
            return "invalid", None
    match = VALID.fullmatch(branch)
    if match is None:
        return "invalid", None
    return "registration", match.group(1)


def is_native_registration(branch: str) -> bool:
    return registration_family(branch)[0] in ("registration", "auxiliary")
