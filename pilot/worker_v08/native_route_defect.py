"""T23 trusted route-only Python runtime migrations and failure classification.

Never classify a proposed-code failure as a route defect. Only exact allowlisted
infrastructure BLOCKED codes from trusted acceptance tools can be forgiven.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

SCHEMA = "LF_NATIVE_ROUTE_PYTHON_FIX_V1"
TASK = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
LEGACY = frozenset(("python", "python3", "python3.12"))
PINNED = "lf-python"
ROUTE_TOOLS = frozenset({
    "pilot/orchestrator/contract_validate.py",
    "pilot/orchestrator/infra_validate.py",
    "pilot/worker_v08/playwright_gate.py",
    "standards/tools/stack_checks.py",
})
# These are environment/tool availability errors, NOT malformed user code.
ROUTE_BLOCK_CODES = frozenset({
    "CONTRACT_SPEC_VALIDATOR_UNAVAILABLE",
    "INFRA_DEPENDENCY_UNAVAILABLE",
    "PYTHON_RUNTIME_UNAVAILABLE",
    "PLAYWRIGHT_BROWSER_UNAVAILABLE",
})
BLOCK = re.compile(r"^BLOCKED:([A-Z][A-Z0-9_]{0,79})(?:\n|$)")
PROOF_KEYS = frozenset({"task_id", "attempt", "task_pack_sha256", "run_id"})


def canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def sha(obj: dict) -> str:
    return hashlib.sha256(canonical(obj)).hexdigest()


def convert(record: dict) -> tuple[dict, int]:
    """Only change acceptance argv[0]; keep every other registration field byte-equivalent."""
    result = json.loads(canonical(record))
    spec = result.get("task_spec")
    if not isinstance(spec, dict) or not isinstance(spec.get("acceptance_commands"), list):
        raise ValueError("TEMPLATE_PYTHON_NO_FIJADO:UNKNOWN")
    count = 0
    for cmd in spec["acceptance_commands"]:
        if not isinstance(cmd, dict) or not isinstance(cmd.get("argv"), list) or not cmd["argv"]:
            raise ValueError("TEMPLATE_PYTHON_NO_FIJADO:UNKNOWN")
        argv = cmd["argv"]
        if argv[0] in LEGACY:
            argv[0] = PINNED
            count += 1
        elif isinstance(argv[0], str) and (Path(argv[0]).name == "python"
                                           or Path(argv[0]).name.startswith("python3")):
            raise ValueError("TEMPLATE_PYTHON_NO_FIJADO:UNKNOWN")
    return result, count


def classify(feedback: dict, original: dict) -> bool:
    """A pure visible-result classifier; no oracle or proposal content is examined."""
    if not isinstance(feedback, dict) or feedback.get("kind") != "VISIBLE_ACCEPTANCE_ONLY":
        return False
    commands = feedback.get("commands")
    if not isinstance(commands, list) or not commands:
        return False
    registered = original.get("task_spec", {}).get("acceptance_commands", [])
    if not isinstance(registered, list):
        return False
    by_name = {x.get("name"): x.get("argv") for x in registered
               if isinstance(x, dict) and isinstance(x.get("name"), str)}
    if len(by_name) != len(registered):
        return False
    failures = 0
    for row in commands:
        if not isinstance(row, dict) or row.get("status") not in ("PASS", "FAIL"):
            return False
        if row["status"] == "PASS":
            continue
        failures += 1
        argv = by_name.get(row.get("name"))
        if (not isinstance(argv, list) or len(argv) < 2
                or argv[0] not in LEGACY | {PINNED}
                or argv[1] not in ROUTE_TOOLS
                or row.get("reason") != "EXIT_NONZERO"
                or type(row.get("returncode")) is not int
                or row["returncode"] == 0):
            return False
        stderr = row.get("stderr_excerpt")
        if not isinstance(stderr, str):
            return False
        matched = BLOCK.fullmatch(stderr.strip() + "\n")
        if matched is None or matched.group(1) not in ROUTE_BLOCK_CODES:
            return False
    return failures > 0


def migration(task: str, original: dict, fixed: dict,
              legacy_pack: str, current_pack: str, source_run: int,
              proposal_sha: str, base_sha: str) -> dict:
    if (not TASK.fullmatch(task) or not SHA64.fullmatch(legacy_pack)
            or not SHA64.fullmatch(current_pack) or not SHA40.fullmatch(proposal_sha)
            or not SHA40.fullmatch(base_sha) or type(source_run) is not int
            or source_run <= 0):
        raise ValueError("ROUTE_FIX_MIGRATION_INVALID")
    actual, changes = convert(original)
    if changes < 1 or actual != fixed:
        raise ValueError("ROUTE_FIX_SCOPE_INVALID")
    if (original["task_spec"]["base_head_sha"] != base_sha
            or fixed["task_spec"]["base_head_sha"] != base_sha):
        raise ValueError("ROUTE_FIX_BASE_DRIFT")
    return {
        "schema_version": SCHEMA,
        "task": task, "source_run_id": source_run,
        "proposal_commit_sha": proposal_sha,
        "base_head_sha": base_sha,
        "legacy_registration_sha256": sha(original),
        "corrected_registration_sha256": sha(fixed),
        "legacy_task_pack_sha256": legacy_pack,
        "corrected_task_pack_sha256": current_pack,
        "launcher_changes": changes,
        "legacy_launchers": [[i, cmd["argv"][0]] for i, cmd in
                             enumerate(original["task_spec"]["acceptance_commands"])
                             if cmd["argv"][0] in LEGACY],
    }


def verified_migration(root: Path, task: str, record: dict,
                       *, proposal_sha: str | None = None) -> dict | None:
    """Return trusted compatibility mapping only if the fixed record is exact."""
    if not TASK.fullmatch(task):
        return None
    file = root / "pilot/worker_v08/route_migrations" / (task + ".json")
    if file.is_symlink() or not file.is_file() or file.stat().st_size > 4096:
        return None
    try:
        data = json.loads(file.read_text("utf-8"))
    except (OSError, UnicodeError, ValueError):
        return None
    allowed = {
        "schema_version", "task", "source_run_id", "proposal_commit_sha",
        "base_head_sha", "legacy_registration_sha256",
        "corrected_registration_sha256", "legacy_task_pack_sha256",
        "corrected_task_pack_sha256", "launcher_changes", "legacy_launchers",
    }
    if (not isinstance(data, dict) or set(data) != allowed
            or data.get("schema_version") != SCHEMA or data.get("task") != task
            or data.get("corrected_registration_sha256") != sha(record)
            or record["task_spec"]["base_head_sha"] != data.get("base_head_sha")
            or not SHA64.fullmatch(data.get("legacy_task_pack_sha256") or "")
            or not SHA64.fullmatch(data.get("corrected_task_pack_sha256") or "")
            or (proposal_sha is not None and data.get("proposal_commit_sha") != proposal_sha)):
        return None
    if (type(data.get("launcher_changes")) is not int or data["launcher_changes"] < 1
            or not isinstance(data.get("legacy_launchers"), list)
            or len(data["legacy_launchers"]) != data["launcher_changes"]):
        return None
    old = json.loads(canonical(record))
    commands = old["task_spec"]["acceptance_commands"]
    seen = set()
    for entry in data["legacy_launchers"]:
        if (not isinstance(entry, list) or len(entry) != 2
                or type(entry[0]) is not int or entry[0] in seen
                or not 0 <= entry[0] < len(commands) or entry[1] not in LEGACY
                or commands[entry[0]]["argv"][0] != PINNED):
            return None
        seen.add(entry[0])
        commands[entry[0]]["argv"][0] = entry[1]
    corrected, count = convert(old)
    if (corrected != record or count != data["launcher_changes"]
            or sha(old) != data.get("legacy_registration_sha256")
            or not SHA40.fullmatch(data.get("proposal_commit_sha") or "")):
        return None
    return data
