#!/usr/bin/env python3
"""CP3.6 trusted Train/native-run event consumer.

Works from clean trusted main, never from proposal-branch code. A verified
integration merge releases successors only via preparation draft PRs; owner
alone labels and the Train alone merges. Three spent failed attempts produce
an immediate BLOCKED receipt plus a governed draft state PR (not a direct main
write). Missing manifests, evidence and encrypted holdouts fail closed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from chain_contract import (ChainBlocked, BLOCK_CODE, attest_merge, blocked_state,
                            progress, validate_plan, verified_failures, deny)
from native_lot_registration import canonical
from native_verified_integration import next_chg
from native_lot_binding import next_ready

sys.path.insert(0, str(ROOT / "pilot/worker_v08"))

ROOT = Path(__file__).resolve().parents[2]
REPO = "paulozterra/lf-programming-sandbox"
TRAIN = ".github/workflows/sandbox-train.yml"
NATIVE = ".github/workflows/worker-native.yml"
MERGE_MESSAGE = re.compile(r"Merge PR #([1-9][0-9]*) via sandbox-train")
SAFE_ID = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")


def run(*args: str, cwd: Path = ROOT, check: bool = True) -> str:
    try:
        p = subprocess.run(list(args), cwd=cwd, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        deny("COMMAND_UNAVAILABLE")
    if check and p.returncode:
        deny("COMMAND_FAILED:" + args[0])
    return p.stdout.strip()


def api(path: str) -> dict:
    raw = run("gh", "api", f"repos/{REPO}/{path}")
    try:
        parsed = json.loads(raw)
    except ValueError:
        deny("GITHUB_RESPONSE_INVALID")
    if not isinstance(parsed, dict):
        deny("GITHUB_RESPONSE_INVALID")
    return parsed


def check_main() -> str:
    head = run("git", "rev-parse", "HEAD")
    if (head != run("git", "rev-parse", "origin/main")
            or head != run("git", "ls-remote", "origin", "refs/heads/main").split()[0]
            or run("git", "status", "--porcelain")):
        deny("MAIN_DRIFT")
    return head


def event_kind(event_run_id: int, head: str) -> str:
    event = api(f"actions/runs/{event_run_id}")
    path = (event.get("path") or "").split("@")[0]
    if (event.get("id") != event_run_id or event.get("status") != "completed"
            or event.get("run_attempt") != 1 or
            event.get("repository", {}).get("full_name") != REPO
            or event.get("head_branch") != "main"):
        deny("SOURCE_WORKFLOW_UNTRUSTED")
    if path == TRAIN and event.get("conclusion") == "success":
        return "TRAIN"
    if path == NATIVE and event.get("conclusion") == "failure":
        return "NATIVE_FAIL"
    return "IRRELEVANT"


def merged_integration(head: str) -> tuple[dict, set[str]]:
    message = run("git", "log", "-1", "--format=%s")
    found = MERGE_MESSAGE.fullmatch(message)
    if found is None:
        deny("HEAD_NOT_TRAIN_MERGE")
    parents = run("git", "rev-list", "--parents", "-n", "1", head).split()
    if len(parents) != 3 or parents[0] != head:
        deny("HEAD_NOT_TWO_PARENT_MERGE")
    pr = api(f"pulls/{int(found.group(1))}")
    if pr.get("merge_commit_sha") != head or pr.get("head", {}).get("ref", "").startswith(
            "lf/native-integration/") is False:
        deny("NOT_NATIVE_INTEGRATION")
    changed = set(run("git", "diff", "--name-only", parents[1], head).splitlines())
    return pr, changed


def plans() -> list[tuple[str, dict, dict, dict]]:
    base = ROOT / "pilot/orchestrator/chain_plans"
    if not base.exists():
        return []
    rows = []
    for file in sorted(base.glob("*.json")):
        if file.is_symlink() or not SAFE_ID.fullmatch(file.stem):
            deny("CHAIN_PLAN_PATH_INVALID")
        request = file.stem
        folder = ROOT / "pilot/runs" / request
        if folder.is_symlink():
            deny("CHAIN_RUN_SYMLINK")
        for path in (folder / "lots.json", folder / "state.json"):
            if not path.is_file() or path.is_symlink():
                deny("CHAIN_INPUT_MISSING")
        plan = json.loads(file.read_text("utf-8"))
        lots = json.loads((folder / "lots.json").read_text("utf-8"))
        state = json.loads((folder / "state.json").read_text("utf-8"))
        if state.get("stage") not in ("LOTS_PLANNED", "BLOCKED"):
            deny("CHAIN_STAGE_INVALID")
        if state.get("lots_sha256") != hashlib.sha256(canonical(lots)).hexdigest():
            deny("CHAIN_STATE_LOTS_DRIFT")
        bindings = validate_plan(plan, lots, request)
        rows.append((request, lots, state, bindings))
    return rows


def first_parent_merges() -> list[tuple[str, dict, set[str]]]:
    # Bound history. Chains must be short-lived and owner-enrolled. A chain
    # whose origin is outside the window needs manual review, not inferred PASS.
    revisions = run("git", "log", "--first-parent", "-n", "75",
                    "--format=%H%x09%s").splitlines()
    results = []
    for record in revisions:
        try:
            sha, message = record.split("\t", 1)
        except ValueError:
            deny("GIT_HISTORY_INVALID")
        match = MERGE_MESSAGE.fullmatch(message)
        if not match:
            continue
        # Avoid unaudited broad PR scans and unnecessary GitHub API calls.
        body = run("git", "log", "-1", "--format=%B", sha)
        if "[CP3.5]" not in body or "Verified native" not in body:
            continue
        pr = api(f"pulls/{int(match.group(1))}")
        if pr.get("head", {}).get("ref", "").startswith("lf/native-integration/"):
            parents = run("git", "rev-list", "--parents", "-n", "1", sha).split()
            if len(parents) != 3 or parents[0] != sha:
                deny("MERGE_PARENT_INVALID")
            changes = set(run("git", "diff", "--name-only",
                              parents[1], sha).splitlines())
            results.append((sha, pr, changes))
    return list(reversed(results))


def completed_lots(lots: dict, bindings: dict, history: list[tuple]) -> dict:
    result = {}
    for sha, pr, changed in history:
        # Ignore other explicitly bound chains, but reject spoofed integration
        # for a task belonging to this chain.
        branch = pr.get("head", {}).get("ref", "")
        if not any(branch.startswith("lf/native-integration/" + row["task_name"] + "-run-")
                   for row in bindings.values()):
            continue
        lot_id, receipt = attest_merge(sha, pr, lots, bindings, changed)
        if lot_id in result:
            deny("DUPLICATE_LOT_MERGE")
        lot = next(item for item in lots["lots"] if item["id"] == lot_id)
        if not set(lot["depends_on"]).issubset(result):
            deny("OUT_OF_ORDER_MERGE")
        for path in receipt["expected_files"]:
            run("git", "cat-file", "-e", sha + ":" + path)
        result[lot_id] = receipt
    return result


def failed_lots(bindings: dict) -> dict[str, list[int]]:
    # The upstream native_run_history proof-reader handles signed artifact
    # redirects without passing credentials to storage and never opens oracles.
    from native_run_history import _artifact_json, _recognized_run
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        deny("GITHUB_TOKEN_MISSING")
    result = {}
    for page in range(1, 11):
        response = api(f"actions/workflows/worker-native.yml/runs?per_page=100&page={page}")
        if response.get("total_count", 0) > 1000:
            deny("RUN_HISTORY_TOO_LARGE")
        if page == 1:
            history = []
        history.extend(response.get("workflow_runs", []))
        if len(history) >= response.get("total_count", 0):
            break
    else:
        deny("RUN_HISTORY_INCOMPLETE")
    for lot, binding in bindings.items():
        task = binding["task_name"]
        failures = [r for r in history if _recognized_run(r, task)
                    and r.get("conclusion") == "failure"]
        proofs = {}
        for entry in failures:
            proof = _artifact_json(REPO, token, entry["id"])
            proofs[entry["id"]] = proof
        result[lot] = verified_failures(task, failures, proofs)
    return result


def chg(root: Path, number: int, request: str, reason: str,
        changed: list[str]) -> Path:
    ident = f"CHG-{number:04d}"
    payload = {
        "schema_version": "LF_STANDARD_CHANGE_V1",
        "change_id": ident,
        "title": f"CP3.6: encadenamiento gobernado {request}",
        "change_class": "ADDITIVE",
        "trigger": {"kind": "OWNER", "reference": "Paulo 2026-11-11 CP3.6 encadenamiento automático"},
        "reason": reason,
        "artifacts": [],
        "affected": {"rule_ids": [], "term_ids": [],
                     "paths": sorted(set(changed + [f"standards/changes/{ident}.json",
                                                   "standards/CAMBIOS.md"]))},
        "existing_code_impact": {"mode": "NEW_OR_MODIFIED_ONLY",
                                 "baseline_ref": "standards/baseline/",
                                 "expected_direction": "NON_INCREASING"},
        "security_pin_invalidation": {"invalidates": False, "affected_artifacts": []},
        "requested_by": "agent:gpt", "approved_by": "paulozterra",
        "evidence": {"pr_url": ""},
    }
    path = root / f"standards/changes/{ident}.json"
    if path.exists():
        deny("CHG_EXISTS")
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", "utf-8")
    run("python3", "standards/tools/changes.py", "render", cwd=root)
    return path


def draft(root: Path, branch: str, request: str, paths: list[str],
          reason: str, title: str) -> dict:
    # Caller has already committed the prepared native task on this branch.
    number = next_chg(root)
    entry = chg(root, number, request, reason, paths)
    run("git", "add", "--", *paths, str(entry.relative_to(root)), "standards/CAMBIOS.md", cwd=root)
    run("git", "commit", "-m", f"[CP3.6][CHG-{number:04d}] {title}", cwd=root)
    from native_verified_integration import confirm_class_after_commit
    confirm_class_after_commit(root, entry)
    if run("git", "ls-remote", "origin", "refs/heads/main", cwd=root).split()[0] != run("git", "merge-base", "origin/main", "HEAD", cwd=root):
        deny("MAIN_MOVED_BEFORE_DRAFT")
    run("git", "push", "--set-upstream", "origin", branch, cwd=root)
    body = (f"CP3.6 · {reason}\n\n"
            f"CHG-{number:04d}; revisión independiente Claude, "
            f"Paulo decide ready-to-merge, Train fusiona. "
            f"No merge ni etiqueta automáticos.")
    url = run("gh", "pr", "create", "--repo", REPO, "--base", "main",
              "--head", branch, "--draft",
              "--title", f"[DRAFT][CP3.6][CHG-{number:04d}] {title}",
              "--body", body, cwd=root)
    document = json.loads(entry.read_text("utf-8"))
    document["evidence"]["pr_url"] = url
    entry.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", "utf-8")
    run("python3", "standards/tools/changes.py", "render", cwd=root)
    run("git", "add", "--", str(entry.relative_to(root)), "standards/CAMBIOS.md", cwd=root)
    run("git", "commit", "-m", "[CP3.6] link reviewable draft evidence", cwd=root)
    run("python3", "standards/tools/changes.py", "check", "--base", "origin/main", cwd=root)
    run("git", "push", "origin", branch, cwd=root)
    run("gh", "workflow", "run", "ci.yml", "--repo", REPO, "--ref", branch, cwd=root)
    return {"draft_pr": url, "head_sha": run("git", "rev-parse", "HEAD", cwd=root)}


def worktree(base: str, branch: str, callback):
    with tempfile.TemporaryDirectory(prefix="cp36-") as temp:
        directory = Path(temp) / "checkout"
        run("git", "worktree", "add", "--detach", str(directory), base)
        try:
            run("git", "switch", "-c", branch, cwd=directory)
            return callback(directory)
        finally:
            run("git", "worktree", "remove", "--force", str(directory))


def prepare_successor(request: str, binding: dict, completed: dict, head: str) -> dict:
    task = binding["task_name"]
    branch = f"lf/native-registration/{task}-{head[:12]}"
    if run("git", "ls-remote", "--heads", "origin", branch):
        return {"status": "ALREADY_PREPARED", "branch": branch}
    def process(root: Path):
        folder = root / "pilot/orchestrator"
        template_path = root / binding["template_path"]
        metadata_path = root / binding["holdout_metadata_path"]
        for file in (template_path, metadata_path):
            if not file.is_file() or file.is_symlink():
                deny("PREPARATION_INPUT_MISSING")
        template = json.loads(template_path.read_text("utf-8"))
        if not isinstance(template, dict) or not isinstance(template.get("task_spec"), dict):
            deny("PREPARATION_TEMPLATE_INVALID")
        # Bind to NEW merged main; no stale sha from a prior lot.
        from native_lot_registration import canonical
        spec = template["task_spec"]
        spec["base_head_sha"] = head
        # source snapshot is computed by prepare_native_lot before registration.
        from native_verified_integration import command
        sys.path.insert(0, str(root / "vendor/programming-agent/src"))
        from programming_agent_runner.hashutil import source_snapshot_sha256
        spec["source_snapshot_sha256"] = source_snapshot_sha256(root)
        template_json = Path(tempfile.mkdtemp(prefix="cp36-template-")) / "task.json"
        try:
            template_json.write_bytes(canonical(template))
            with tempfile.TemporaryDirectory(prefix="cp36-proofs-") as proofs_temp:
                args = []
                for lot_id, proof in sorted(completed.items()):
                    file = Path(proofs_temp) / (lot_id + ".json")
                    file.write_bytes(canonical({k: proof[k] for k in
                        ("lot_id", "merge_sha", "expected_files")}))
                    args.extend(["--handoff-proof", str(file)])
                command_line = [
                    "python3", "pilot/orchestrator/prepare_native_lot.py",
                    "--root", str(root), "--request-id", request,
                    "--lot-id", binding["lot_id"], "--task-name", task,
                    "--template", str(template_json),
                    "--holdout-metadata", str(metadata_path), *args]
                raw = run(*command_line, cwd=root)
                prepared = json.loads(raw)
        finally:
            template_json.unlink(missing_ok=True)
            template_json.parent.rmdir()
        if prepared.get("result") != "CP35_PREPARED_NO_MODEL_NO_PUSH":
            deny("PREPARATION_NOT_VERIFIED")
        artifact_dir = os.environ.get("CP36_PACK_OUT")
        if artifact_dir:
            import shutil
            selected = root / "pilot/runs" / request / "proposal_requests"
            destination = Path(artifact_dir)
            destination.mkdir(parents=True, exist_ok=True)
            for suffix in (".task-pack.json", ".proposal-request.json"):
                file = selected / (task + suffix)
                if not file.is_file() or file.is_symlink():
                    deny("EXPORTED_PACK_MISSING")
                shutil.copyfile(file, destination / file.name)
        paths = [f".lf/worker-context/{task}/{n}" for n in
                 ("profile.md", "skills.md", "receipt.json")]
        paths += [f"pilot/worker_v08/native_tasks/{task}.json"]
        review = draft(root, branch, request, paths,
                       f"Registration from main {head} for lot {binding['lot_id']}; "
                       f"task {task}; base {prepared['base_head_sha']}; "
                       f"generated by prepare_native_lot.py; no model.",
                       f"native registration {task}")
        return {"status": "DRAFT_PREPARED", "task": task, **review,
                "task_pack_sha256": prepared["task_pack_sha256"]}
    return worktree(head, branch, process)


def block_request(request: str, state: dict, result: dict, head: str) -> dict:
    branch = f"lf/chain-blocked/{request}-{head[:12]}"
    if run("git", "ls-remote", "--heads", "origin", branch):
        return {"status": "BLOCKED_ALREADY_RECORDED", "branch": branch}
    def process(root: Path):
        target = root / "pilot/runs" / request / "state.json"
        target.write_bytes(canonical(blocked_state(state, result)))
        review = draft(root, branch, request, [target.relative_to(root).as_posix()],
                       BLOCK_CODE + " after three Actions-proven failed attempts; "
                       "state update requires owner-reviewed Train merge.",
                       f"BLOCKED {request} ({BLOCK_CODE})")
        return {"status": "BLOCKED_PENDING_OWNER_MERGE", "reason_code": BLOCK_CODE,
                **review}
    return worktree(head, branch, process)


def process(event_run_id: int) -> list[dict]:
    head = check_main()
    kind = event_kind(event_run_id, head)
    if kind == "IRRELEVANT":
        return [{"status": "IGNORED_SOURCE_EVENT"}]
    all_plans = plans()
    if not all_plans:
        return [{"status": "NO_OWNER_REGISTERED_CHAIN_PLANS"}]
    history = first_parent_merges()
    current_pr = None
    if kind == "TRAIN":
        try:
            current_pr, _ = merged_integration(head)
        except ChainBlocked as exc:
            if str(exc) in ("CP36_NOT_NATIVE_INTEGRATION", "CP36_HEAD_NOT_TRAIN_MERGE"):
                return [{"status": "IGNORED_UNRELATED_TRAIN_MERGE"}]
            raise
    outcomes = []
    for request, lots, state, bindings in all_plans:
        if state.get("stage") == "BLOCKED":
            outcomes.append({"request": request, "status": "ALREADY_BLOCKED"})
            continue
        completed = completed_lots(lots, bindings, history)
        failures = failed_lots(bindings)
        result = progress(lots, completed, failures, bindings)
        if result["stage"] == "BLOCKED":
            outcomes.append({"request": request, **block_request(request, state, result, head)})
            continue
        if kind != "TRAIN":
            continue
        # Do not schedule all ready lots after an unrelated train merge.
        if current_pr is None:
            continue
        current_task = current_pr.get("head", {}).get("ref", "").split("-run-")[0]
        merged_tasks = {receipt["task_name"] for receipt in completed.values()
                        if receipt["merge_sha"] == head}
        if not merged_tasks or current_task not in {
                "lf/native-integration/" + t for t in merged_tasks}:
            continue
        for lot_id in result["ready_lot_ids"]:
            lot = next(x for x in lots["lots"] if x["id"] == lot_id)
            if not (set(lot["depends_on"]) & set(
                    receipt["lot_id"] for receipt in completed.values()
                    if receipt["merge_sha"] == head)):
                continue
            outcomes.append({"request": request, "lot_id": lot_id,
                             **prepare_successor(request, bindings[lot_id] | {
                                 "lot_id": lot_id}, completed, head)})
    return outcomes or [{"status": "NO_RELEASE_OR_BLOCK"}]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-run-id", required=True, type=int)
    args = parser.parse_args()
    try:
        if (os.environ.get("GITHUB_REPOSITORY") != REPO or
                not os.environ.get("GH_TOKEN") or args.source_run_id <= 0):
            deny("TRUSTED_RUN_ENV_REQUIRED")
        print(json.dumps(process(args.source_run_id), sort_keys=True))
    except (ChainBlocked, OSError, ValueError, KeyError) as exc:
        code = str(exc) if isinstance(exc, ChainBlocked) else "CP36_UNEXPECTED_FAILURE"
        print(code, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
