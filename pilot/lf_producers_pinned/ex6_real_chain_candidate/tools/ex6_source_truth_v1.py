"""EX6 source-of-truth: only exact immutable sandbox public data and original ZIPs.

No EX5C fixtures, no undocumented successful command receipts, no oracle content.
The output contains no guessed prices, acceptance, reviewer decisions or authority.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence"
SRC = Path(__file__).with_name("ex6_real_world_v1.py")
_loader = importlib.util.spec_from_file_location("h4_ex6_public_reader", SRC)
_reader = importlib.util.module_from_spec(_loader)
_loader.loader.exec_module(_reader)

BLOBS = {
    "ex6_base_REMINDERS_SPEC.md": "01895c09cb6b3983f4fa2ab7fc1db628b2bbaa72",
    "ex6_task_registration.json": "15fd94d238215dbbc21a3bdc3cc719028c8513e7",
}
SPEC_REF = "ex6://source/spec/" + _reader.BASE_SHA + "#lote-d"
TASK_REF = "ex6://source/task/912c4ad9ea71f48edbd1ac58089441f9ed2c3449"
PROPOSAL_REF = "ex6://source/proposal/" + _reader.PROPOSAL_COMMIT_SHA
RUN_REF = "ex6://run/42674262914"
EXPECTED_HOLDOUT = "c2b583ebcc14e8e73e1b66eff38d86dd3814b75e5f5e1857de65deee5c8b1a57"
REQUIREMENTS = ("REM-D1", "REM-D2", "REM-D3", "REM-D4")
FORBIDDEN_VALUES = ("ex5c", "lote-c")
NEW_FILE_MARKER = re.compile(r"(?m)^diff --git a/(\S+) b/(\S+)\nnew file mode 100644\n(?:index [^\n]+\n)?--- /dev/null\n\+\+\+ b/\1\n(@@ -0,0 \+(?:1,)?\d+ @@)")
HUNK = re.compile(r"(?m)^@@ -(?P<oldstart>\d+)(?:,(?P<oldcount>\d+))? \+(?P<newstart>\d+)(?:,(?P<newcount>\d+))? @@.*$")


class EX6SourceBlocked(ValueError):
    pass


def block(reason: str):
    raise EX6SourceBlocked(reason)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def canon(data) -> bytes:
    return json.dumps(data, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")


def pinned_public_file(name: str, directory: Path = EVIDENCE) -> bytes:
    path = directory / name
    if not path.is_file() or path.is_symlink():
        block("EX6_PUBLIC_SOURCE_MISSING:" + name)
    data = path.read_bytes()
    if git_blob_sha(data) != BLOBS[name]:
        block("EX6_PUBLIC_SOURCE_BLOB_MISMATCH:" + name)
    return data


def real_hunks(patch: bytes) -> list[dict]:
    text = patch.decode("utf-8", "strict")
    headers = list(re.finditer(r"(?m)^diff --git a/(\S+) b/(\S+)\n", text))
    if len(headers) != 3:
        block("EX6_REAL_HUNK_COUNT_INVALID")
    out = []
    for index, match in enumerate(headers):
        fragment = text[match.start(): headers[index + 1].start() if index + 1 < len(headers) else len(text)]
        path = match.group(1)
        if (path != match.group(2) or path not in _reader.EXACT_PATHS
            or "new file mode 100644\n" not in fragment.split("@@", 1)[0]
            or "--- /dev/null\n" not in fragment
            or "+++ b/" + path + "\n" not in fragment):
            block("EX6_REAL_HUNK_SCOPE_INVALID")
        hunk_matches = list(HUNK.finditer(fragment))
        if len(hunk_matches) != 1:
            block("EX6_REAL_HUNK_HEADER_INVALID")
        h = hunk_matches[0]
        before = int(h.group("oldcount") or 1)
        after = int(h.group("newcount") or 1)
        if (int(h.group("oldstart")) != 0 or before != 0
            or int(h.group("newstart")) != 1 or after <= 0):
            block("EX6_REAL_HUNK_SPAN_INVALID")
        added = fragment[h.end():].removeprefix("\n")
        lines = added.splitlines(keepends=True)
        if len(lines) != after or not all(x.startswith("+") for x in lines):
            block("EX6_REAL_HUNK_BODY_INVALID")
        new_bytes = "".join(x[1:] for x in lines).encode("utf-8")
        # Bind patch additions to Git blob objects named in original diff index.
        index_match = re.search(r"(?m)^index 0000000\.\.([0-9a-f]{7,40})$", fragment)
        if not index_match or not git_blob_sha(new_bytes).startswith(index_match.group(1)):
            block("EX6_REAL_HUNK_BLOB_MISMATCH")
        out.append({
            "hunk_id": f"EX6-HUNK-{index + 1:03d}",
            "path": path, "change_type": "ADDED",
            "old_start": 0, "old_count": 0, "new_start": 1, "new_count": after,
            "content_sha256": sha(new_bytes),
            "git_blob_oid": git_blob_sha(new_bytes),
            "header_ref": RUN_REF + "#verified-patch/" + str(index + 1),
            "source_ref": SPEC_REF,
            "requirements": {
                "ReminderStats.java": ["REM-D1"],
                "ReminderStatsService.java": ["REM-D2"],
                "ReminderStatsController.java": ["REM-D3", "REM-D4"],
            }[Path(path).name],
            "batch_ref": "ex6://batch/EX6-SOL-001",
            "scope_ref": "ex6://scope/" + path,
        })
    if sorted(x["path"] for x in out) != _reader.EXACT_PATHS:
        block("EX6_REAL_HUNK_PATH_COVERAGE_DRIFT")
    return out


def source_truth(root: Path = EVIDENCE) -> dict:
    public = _reader.load_evidence(root)
    members = _reader.read_bundle(root)
    complete_spec = pinned_public_file("ex6_base_REMINDERS_SPEC.md", root).decode("utf-8")
    if complete_spec.count("## Lote D —") != 1:
        block("EX6_BASE_SPEC_LOTE_D_NOT_UNIQUE")
    lote = "## Lote D —" + complete_spec.split("## Lote D —", 1)[1]
    registration = json.loads(pinned_public_file("ex6_task_registration.json", root))
    if (lote.count("## Lote D") != 1 or
        any(lote.count(req) != 1 for req in REQUIREMENTS)):
        block("EX6_LOTE_D_REQUIREMENT_COVERAGE_INVALID")
    if set(registration) != {"task_spec", "holdout_sha256"}:
        block("EX6_TASK_REGISTRATION_SHAPE_INVALID")
    task = registration["task_spec"]
    if (task.get("base_head_sha") != _reader.BASE_SHA
        or task.get("task_id") != "LF-WORKER-NATIVE-EX6"
        or task.get("max_attempts") != 1 or task.get("max_changed_files") != 3
        or task.get("allow_deletions") is not False
        or sorted(task.get("write_path_patterns", [])) != _reader.EXACT_PATHS
        or registration["holdout_sha256"] != EXPECTED_HOLDOUT):
        block("EX6_TASK_SCOPE_OR_HOLDOUT_DRIFT")
    protected = task.get("protected_path_patterns")
    if not isinstance(protected, list) or not protected or any(
        not isinstance(p, str) or not p for p in protected):
        block("EX6_PROTECTED_PATHS_INVALID")
    if any(p in protected for p in _reader.EXACT_PATHS):
        block("EX6_ALLOW_PROTECTED_COLLISION")
    # The verified patch ZIP is the ONLY source for hunks and code bytes.
    # The native proposal envelope is not a public Worker receipt and can
    # differ in Git's "index" metadata without changing the actual patch.
    original_patch = members["worker.patch"]
    if (public["patch_sha256"] != sha(original_patch)
        or json.loads(members["status.json"]).get("status") != "PASS"):
        block("EX6_PASS_OR_PATCH_DRIFT")
    hunks = real_hunks(original_patch)
    cost = json.loads(members["cost.json"])
    proof = json.loads(members["attempt-proof.json"])
    status = json.loads(members["status.json"])
    feedback = json.loads(members["feedback.json"])
    outcome = {
        "source_ref": SPEC_REF, "task_ref": TASK_REF, "proposal_ref": PROPOSAL_REF,
        "run_ref": RUN_REF, "repo_full_name": _reader.REPO,
        "base_head_sha": task["base_head_sha"],
        "source_snapshot_sha256": task["source_snapshot_sha256"],
        "task_pack_sha256": status["task_pack_sha256"],
        "proposal_sha256": status["proposal_sha256"],
        "holdout_sha256": registration["holdout_sha256"],
        "holdout_result": status["status"],  # reported PASS, not blind oracle content
        "requirements": list(REQUIREMENTS),
        "acceptance_commands": task["acceptance_commands"],
        "write_paths": sorted(task["write_path_patterns"]),
        "protected_paths": list(protected),
        "hunks": hunks,
        "patch_sha256": sha(original_patch),
        "cost": cost,
        "attempt_proof": proof,
        "status": status,
        "feedback": feedback,
        "executor_mode": "GPT_NATIVE",
        "api_calls": cost["api_calls"],
        "incremental_api_cost": str(cost["total_usd"]),
        "subscription_cost": cost["subscription_cost"],
        "authority": "REAL_SANDBOX_UNAUTHENTICATED",
        "receipt_authenticated": False,
        "handoff_allowed": False,
        "production_authority": False,
    }
    # Strictly scan ALL string values (including references) supplied downstream.
    def inspect(v):
        if isinstance(v, str) and any(x in v.lower() for x in FORBIDDEN_VALUES):
            block("EX6_FOREIGN_EXERCISE_CONTAMINATION")
        if isinstance(v, dict):
            for z in v.values():
                inspect(z)
        elif isinstance(v, list):
            for z in v:
                inspect(z)
    inspect(outcome)
    return outcome


if __name__ == "__main__":
    truth = source_truth()
    print(json.dumps({
        "source": truth["source_ref"], "base": truth["base_head_sha"],
        "proposal": truth["proposal_sha256"], "hunks": truth["hunks"],
        "authority": truth["authority"], "cost": truth["incremental_api_cost"],
    }, indent=2, sort_keys=True))
