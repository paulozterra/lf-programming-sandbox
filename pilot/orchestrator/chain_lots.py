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
from native_verified_integration import IntegrationBlocked, next_chg
from native_lot_binding import next_ready
from t4_admission import AdmissionBlocked, require_green_base, missing_exam, public_exam_request, registration_variant, protected_test_conflict

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "pilot/worker_v08"))

ROOT = Path(__file__).resolve().parents[2]
REPO = "paulozterra/lf-programming-sandbox"
TRAIN = ".github/workflows/sandbox-train.yml"
NATIVE = ".github/workflows/worker-native.yml"
CI = ".github/workflows/ci.yml"
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
            event.get("repository", {}).get("full_name") != REPO):
        deny("SOURCE_WORKFLOW_UNTRUSTED")
    # The Train is triggered by pull_request:labeled, so the source
    # workflow's head_branch is the PR branch, NOT main. We verify the
    # resulting merge on current main independently below.
    if path == TRAIN and event.get("conclusion") == "success":
        if event.get("event") not in ("pull_request", "workflow_dispatch"):
            deny("TRAIN_SOURCE_EVENT_INVALID")
        if (event.get("event") == "workflow_dispatch"
                and event.get("head_branch") != "main"):
            deny("TRAIN_SOURCE_BRANCH_INVALID")
        return "TRAIN"
    # The Train merge and main CI run concurrently. Reconcile again when
    # exact-main CI finishes: an early BASE_NO_VERDE must not permanently
    # strand a root lot or require a manual workflow dispatch.
    if (path == CI and event.get("head_branch") == "main"
            and event.get("head_sha") == head
            and event.get("event") in ("push", "workflow_dispatch")
            and event.get("conclusion") in ("success", "failure")):
        return "TRAIN"
    # Native Worker always checks out trusted main; fail closed on drift.
    if (path == NATIVE and event.get("conclusion") == "failure"
            and event.get("head_branch") == "main"
            and event.get("event") in ("workflow_run", "workflow_dispatch")):
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


def validated_manual_integration(number: int, head: str) -> str:
    """Accept only a Train merge on the trusted first-parent main ancestry."""
    if type(number) is not int or number <= 0:
        deny("INTEGRATION_PR_INVALID")
    pr = api(f"pulls/{number}")
    sha = pr.get("merge_commit_sha")
    branch = pr.get("head", {}).get("ref", "")
    if (pr.get("number") != number or pr.get("merged") is not True
            or not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha)
            or not re.fullmatch(r"lf/native-integration/[a-z][a-z0-9_-]{0,31}-run-[1-9][0-9]*", branch)
            or pr.get("base", {}).get("ref") != "main"
            or pr.get("base", {}).get("repo", {}).get("full_name") != REPO
            or pr.get("head", {}).get("repo", {}).get("full_name") != REPO):
        deny("MANUAL_INTEGRATION_PR_UNTRUSTED")
    result = subprocess.run(["git", "merge-base", "--is-ancestor", sha, head],
                            cwd=ROOT, capture_output=True, timeout=120)
    if result.returncode:
        deny("MANUAL_INTEGRATION_NOT_ANCESTOR")
    if sha not in set(run("git", "rev-list", "--first-parent", "HEAD").splitlines()):
        deny("MANUAL_INTEGRATION_NOT_TRAIN")
    if run("git", "log", "-1", "--format=%s", sha) != (
            f"Merge PR #{number} via sandbox-train"):
        deny("MANUAL_INTEGRATION_NOT_TRAIN")
    parents = run("git", "rev-list", "--parents", "-n", "1", sha).split()
    if len(parents) != 3 or parents[0] != sha:
        deny("MANUAL_INTEGRATION_NOT_TRAIN")
    return sha


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
        if not any(re.fullmatch(
                r"lf/native-integration/" + re.escape(row["task_name"])
                + r"(?:(?:[2-9]|[1-9][0-9]+))?-run-[1-9][0-9]*", branch)
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
    return path


def draft(root: Path, branch: str, request: str, paths: list[str],
          reason: str, title: str) -> dict:
    # Caller has already committed the prepared native task on this branch.
    number = next_chg(root)
    entry = chg(root, number, request, reason, paths)
    run("git", "add", "--", *paths, str(entry.relative_to(root)), cwd=root)
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
    run("git", "add", "--", str(entry.relative_to(root)), cwd=root)
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


def pending_draft(prefix: str) -> bool:
    """Do not create another draft for the same task/request after main moves."""
    rows = json.loads(run("gh", "pr", "list", "--repo", REPO,
                          "--state", "open", "--limit", "100",
                          "--json", "headRefName"))
    if not isinstance(rows, list):
        deny("PENDING_DRAFT_LIST_INVALID")
    return any(isinstance(item, dict) and
               str(item.get("headRefName", "")).startswith(prefix)
               for item in rows)


def request_missing_exam(request: str, binding: dict, lot: dict) -> dict:
    """Issue public EXAM_REQUEST once, leaving the lot fail-closed.

    Never reads holdout ciphertext or examiner metadata, and never attaches
    any GitHub label to the registration PR.
    """
    title, body = public_exam_request(ROOT, request, binding, lot)
    labels = json.loads(run("gh", "label", "list", "--repo", REPO,
                            "--search", "exam-request", "--limit", "100",
                            "--json", "name"))
    if not isinstance(labels, list) or len(labels) >= 100:
        deny("EXAM_REQUEST_LABELS_UNTRUSTED")
    if not any(isinstance(row, dict) and row.get("name") == "exam-request"
               for row in labels):
        run("gh", "label", "create", "exam-request", "--repo", REPO,
            "--description", "Independent encrypted examination requested",
            "--color", "D4C5F9")
    existing = json.loads(run("gh", "issue", "list", "--repo", REPO,
                              "--state", "all", "--label", "exam-request",
                              "--limit", "100", "--json", "title,number"))
    if not isinstance(existing, list) or len(existing) >= 100:
        deny("EXAM_REQUEST_LIST_UNTRUSTED")
    matches = [row for row in existing
               if isinstance(row, dict) and row.get("title") == title]
    if len(matches) > 1:
        deny("EXAM_REQUEST_DUPLICATE")
    if not matches:
        run("gh", "issue", "create", "--repo", REPO, "--title", title,
            "--body", body, "--label", "exam-request")
    return {"status": "BLOCKED", "reason_code": "EXAMEN_PENDIENTE",
            "task": binding["task_name"]}


def admit_registration(request: str, binding: dict, lot: dict, head: str) -> dict | None:
    """Inspect admission before any generated commit or native preparation."""
    require_green_base(head, api)
    protected_test_conflict(ROOT, lot, binding)
    if missing_exam(ROOT, binding["task_name"]):
        return request_missing_exam(request, binding, lot)
    return None


def prepare_successor(request: str, binding: dict, completed: dict, head: str) -> dict:
    task = binding["task_name"]
    branch = f"lf/native-registration/{task}-{head[:12]}"
    if pending_draft(f"lf/native-registration/{task}-") or run("git", "ls-remote", "--heads", "origin", branch):
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
        # Suffix attempts have an independent immutable native task identity.
        if task != binding.get("original_task_name", task):
            spec["task_id"] = "LF-WORKER-NATIVE-" + task.upper()
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
    if pending_draft(f"lf/chain-blocked/{request}-") or run("git", "ls-remote", "--heads", "origin", branch):
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


def process(event_run_id: int | None = None, integration_pr: int | None = None) -> list[dict]:
    head = check_main()
    manual_sha = (validated_manual_integration(integration_pr, head)
                  if integration_pr is not None else None)
    kind = "TRAIN" if manual_sha is not None else event_kind(event_run_id, head)
    if kind == "IRRELEVANT":
        return [{"status": "IGNORED_SOURCE_EVENT"}]
    all_plans = plans()
    if not all_plans:
        return [{"status": "NO_OWNER_REGISTERED_CHAIN_PLANS"}]
    history = first_parent_merges()
    if manual_sha is not None and not any(sha == manual_sha for sha, _, _ in history):
        deny("MANUAL_INTEGRATION_OUTSIDE_HISTORY")
    # Historical first-parent commits are the proof. Reconcile all merged
    # native integrations so an unrelated Train merge between the source
    # event and this job cannot silently lose a successor.
    outcomes = []
    for request, lots, state, bindings in all_plans:
        if state.get("stage") == "BLOCKED":
            outcomes.append({"request": request, "status": "ALREADY_BLOCKED"})
            continue
        completed = completed_lots(lots, bindings, history)
        if manual_sha is not None and not any(
                proof["merge_sha"] == manual_sha for proof in completed.values()):
            continue  # Requested integration is for a different chain.
        failures = failed_lots(bindings)
        result = progress(lots, completed, failures, bindings)
        if result["stage"] == "BLOCKED":
            outcomes.append({"request": request, **block_request(request, state, result, head)})
            continue
        if kind != "TRAIN":
            continue
        for lot_id in result["ready_lot_ids"]:
            lot = next(x for x in lots["lots"] if x["id"] == lot_id)
            if not set(lot["depends_on"]).issubset(completed):
                continue
            task = bindings[lot_id]["task_name"]
            # Only public/source and template drift can require a new attempt.
            # Never overwrite a registered task or reuse an old examiner SHA.
            registered = ROOT / "pilot/worker_v08/native_tasks" / (task + ".json")
            if registered.exists() or registered.is_symlink():
                def relevant_base_diff(base_sha: str) -> set[str]:
                    run("git", "merge-base", "--is-ancestor", base_sha, head)
                    return set(run("git", "diff", "--name-only", base_sha, head).splitlines())
                candidate = registration_variant(
                    ROOT, task, bindings[lot_id]["template_path"],
                    relevant_base_diff)
            else:
                candidate = task
            if candidate is None:
                continue
            chosen = dict(bindings[lot_id], task_name=candidate,
                          original_task_name=task, lot_id=lot_id)
            if candidate != task:
                metadata = Path(chosen["holdout_metadata_path"])
                chosen["holdout_metadata_path"] = str(
                    metadata.with_name(candidate + metadata.suffix))
            if pending_draft(f"lf/native-registration/{candidate}-"):
                outcomes.append({"request": request, "lot_id": lot_id,
                                 "status": "ALREADY_PREPARED"})
                continue
            admission = admit_registration(request, chosen, lot, head)
            if admission is not None:
                outcomes.append({"request": request, "lot_id": lot_id, **admission})
                continue
            outcomes.append({"request": request, "lot_id": lot_id,
                             **prepare_successor(request, chosen, completed, head)})
    return outcomes or [{"status": "NO_RELEASE_OR_BLOCK"}]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-run-id", type=int)
    parser.add_argument("--integration-pr", type=int)
    args = parser.parse_args()
    try:
        if (os.environ.get("GITHUB_REPOSITORY") != REPO
                or not os.environ.get("GH_TOKEN")
                or (args.integration_pr is None and
                    (args.source_run_id is None or args.source_run_id <= 0))
                or (args.integration_pr is not None and
                    (args.integration_pr <= 0 or args.source_run_id is not None))):
            deny("TRUSTED_RUN_ENV_REQUIRED")
        print(json.dumps(process(args.source_run_id, args.integration_pr), sort_keys=True))
    except (ChainBlocked, IntegrationBlocked, AdmissionBlocked, OSError, ValueError, KeyError) as exc:
        code = (str(exc) if isinstance(exc, (ChainBlocked, IntegrationBlocked, AdmissionBlocked))
                else "CP36_UNEXPECTED_FAILURE")
        print(code, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
