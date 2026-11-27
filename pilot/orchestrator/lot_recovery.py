"""Owner-enrolled, append-only continuation of an exhausted native lot."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

POLICY = "pilot/orchestrator/lot_recovery.json"
TASK = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
REQUEST = re.compile(r"req-[1-9][0-9]*\Z")
LOT = re.compile(r"SOL-[A-Za-z0-9]+\Z")
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
FIELDS = {"request_id", "lot_id", "original_task", "successor_task",
          "original_run_ids", "forgiven_run_ids", "max_additional_attempts",
          "blocked_pr", "blocked_pr_head"}


def require(condition):
    if not condition:
        raise ValueError("LOT_RECOVERY_AUTHORIZATION_INVALID")


def parse(raw):
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            require(key not in obj)
            obj[key] = value
        return obj
    data = json.loads(raw, object_pairs_hook=unique)
    require(isinstance(data, dict) and set(data) == {"schema_version", "recoveries"}
            and data["schema_version"] == "LF_LOT_RECOVERY_V1"
            and isinstance(data["recoveries"], list))
    rows = {}
    tasks = set()
    for row in data["recoveries"]:
        require(isinstance(row, dict) and set(row) == FIELDS)
        req, lot, old, new = (row[k] for k in
                              ("request_id", "lot_id", "original_task", "successor_task"))
        require(all(isinstance(x, str) for x in (req, lot, old, new))
                and REQUEST.fullmatch(req) and LOT.fullmatch(lot)
                and TASK.fullmatch(old) and TASK.fullmatch(new)
                and re.fullmatch(re.escape(old) + r"(?:[2-9]|[1-9][0-9]+)", new))
        spent, forgiven = row["original_run_ids"], row["forgiven_run_ids"]
        require(isinstance(spent, list) and isinstance(forgiven, list)
                and len(spent) == 3
                and all(type(x) is int and x > 0 for x in spent + forgiven)
                and spent == sorted(set(spent))
                and forgiven == sorted(set(forgiven))
                and not set(spent) & set(forgiven)
                and type(row["max_additional_attempts"]) is int
                and row["max_additional_attempts"] == 1
                and type(row["blocked_pr"]) is int and row["blocked_pr"] > 0
                and isinstance(row["blocked_pr_head"], str)
                and SHA40.fullmatch(row["blocked_pr_head"]))
        key = (req, lot)
        require(key not in rows and old not in tasks and new not in tasks)
        tasks.update((old, new))
        rows[key] = row
    return rows


def append_only(previous, current):
    require(all(current.get(key) == row for key, row in previous.items()))


def load(root: Path):
    path = root / POLICY
    missing = not path.exists() and not path.is_symlink()
    # Preserve the no-policy case for non-Git synthetic test roots only.
    if missing and not (root / ".git").exists():
        return {}
    def git(*args):
        return subprocess.check_output(["git", "-C", str(root), *args], timeout=20)
    require(git("rev-parse", "--is-shallow-repository").strip() == b"false")
    commits = git("log", "--first-parent", "--full-history", "--format=%H",
                  "HEAD", "--", POLICY).decode("ascii").splitlines()
    if missing:
        require(not commits)  # a previously enrolled policy must never disappear
        return {}
    require(path.is_file() and not path.is_symlink())
    rows = parse(path.read_bytes())
    require(0 < len(commits) <= 1000)
    prior = {}
    for commit in reversed(commits):
        current = parse(git("show", commit + ":" + POLICY))
        append_only(prior, current)
        prior = current
    require(rows == prior)
    return rows


def for_request(root, request, bindings):
    rows = {lot: row for (req, lot), row in load(root).items() if req == request}
    for lot, row in rows.items():
        require(lot in bindings and bindings[lot]["task_name"] == row["original_task"])
        require(all(b["task_name"] != row["successor_task"] for b in bindings.values()))
    return rows


def for_successor(root, task):
    rows = [r for r in load(root).values() if r["successor_task"] == task]
    require(len(rows) <= 1)
    return rows[0] if rows else None


def schedule_recovery(row, original, successor):
    """Use a separate scheduling projection, not a rewrite of the ledger."""
    require(original == row["original_run_ids"])
    require(isinstance(successor, list) and len(successor) <= 1)
    return not successor


def verify_original(row, prior, forgiven, runs):
    """The Worker independently attests the exhausted original ledger."""
    ordered = sorted(prior, key=lambda proof: proof["attempt"])
    require([p["attempt"] for p in ordered] == [1, 2, 3]
            and [p["run_id"] for p in ordered] == row["original_run_ids"]
            and sorted(forgiven) == row["forgiven_run_ids"])
    for proof in ordered:
        require(proof["task_id"] == row["original_task"]
                and isinstance(proof["task_pack_sha256"], str)
                and SHA64.fullmatch(proof["task_pack_sha256"]))
        matches = [r for r in runs if r.get("id") == proof["run_id"]]
        require(len(matches) == 1 and matches[0].get("status") == "completed"
                and matches[0].get("conclusion") == "failure")


def require_unused(prior):
    if prior:
        raise ValueError("LOT_RECOVERY_ATTEMPT_EXHAUSTED")


def public_task(root, request, task, *, lot=None):
    """Resolve only an owner-enrolled successor to its immutable public template."""
    row = for_successor(root, task)
    if row is None:
        return task
    require(row["request_id"] == request and (lot is None or row["lot_id"] == lot))
    from pilot.config.project_config import storage_path
    folder = storage_path("requests_root", root=root) / request
    path = folder / "chain_plan.json"
    require(path.is_file() and not path.is_symlink() and not folder.is_symlink())
    plan = json.loads(path.read_text("utf-8"))
    require(plan.get("request_id") == request)
    bindings = [b for b in plan["bindings"] if b.get("lot_id") == row["lot_id"]]
    original = row["original_task"]
    expected = (folder / "templates" / f"{original}.task.json").relative_to(root).as_posix()
    require(len(bindings) == 1 and bindings[0].get("task_name") == original
            and bindings[0].get("template_path") == expected)
    return original
