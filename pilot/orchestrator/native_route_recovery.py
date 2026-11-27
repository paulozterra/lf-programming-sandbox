"""T23 trusted CP3.6 repair of route-owned Python acceptance defects.

An Actions-proven feedback artifact is required before a Worker failure can be
classified as ROUTE_DEFECT. No hidden artifact or oracle is ever read. A
generated Draft PR changes only public registrations, package and provenance;
the original proposal branch and encrypted exam remain untouched.
"""
from __future__ import annotations

from pilot.orchestrator.request_lifecycle import RequestStateError
# Resolve the trusted repository package when executed as a script.
import sys as _project_sys
from pathlib import Path as _project_Path
_project_sys.path.insert(0, str(_project_Path(__file__).resolve().parents[2]))
from pilot.config.project_config import ProjectConfigError, storage_path, storage

import hashlib
import json
from pathlib import Path
import re
import tempfile

from pilot.worker_v08.native_feedback_delivery import (
    _run_identity, _artifact_names, read_public, issue_for_task,
)
from pilot.worker_v08.native_route_defect import (
    TASK, SHA40, SCHEMA, canonical, classify, convert,
    migration, verified_migration,
)
from pilot.worker_v08.native_proposal_push_guard import (
    ProposalPushBlocked, validate_proposal_only,
)

RUN_HISTORY = "actions/workflows/worker-native.yml/runs?per_page=100"
RETRY_TITLE = re.compile(
    r"lf-native-route-retry-([a-z][a-z0-9_-]{0,31})-([0-9a-f]{40})\Z")
MARKER = "LF_NATIVE_ROUTE_DEFECT"
MAX_RUNS = 1000


def history(api) -> list[dict]:
    found = []
    for page in range(1, 11):
        path = RUN_HISTORY + ("" if page == 1 else f"&page={page}")
        response = api(path)
        rows = response.get("workflow_runs")
        count = response.get("total_count")
        if (not isinstance(rows, list) or type(count) is not int
                or count > MAX_RUNS or len(rows) > 100):
            raise ValueError("ROUTE_DEFECT_RUN_HISTORY_INCOMPLETE")
        found.extend(rows)
        if len(found) >= count:
            return found
        if not rows:
            break
    raise ValueError("ROUTE_DEFECT_RUN_HISTORY_INCOMPLETE")


def _artifact_payload(run, api, repo: str, event: dict):
    run_id = event["id"]
    jobs = api(f"actions/runs/{run_id}/jobs?per_page=100")
    rows = jobs.get("jobs")
    if (not isinstance(rows, list) or len(rows) != 1 or jobs.get("total_count") != 1
            or rows[0].get("name") != "native"):
        return None
    if not any(isinstance(s, dict)
               and s.get("name") == "Execute original run_verified_worker using native proposal (single attempt)"
               and s.get("conclusion") == "failure"
               for s in rows[0].get("steps", [])):
        return None
    if not _artifact_names(api, run_id):
        return None
    with tempfile.TemporaryDirectory(prefix="t23-route-") as tmp:
        folder = Path(tmp)
        for name in ("native-attempt-proof", "native-visible-feedback-and-cost"):
            dest = folder / name
            dest.mkdir()
            run("gh", "run", "download", str(run_id), "--repo", repo,
                "--name", name, "--dir", str(dest))
        path = folder / "native-attempt-proof/attempt-proof.json"
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 4096:
            return None
        try:
            proof = json.loads(path.read_text("utf-8"))
        except (UnicodeError, ValueError):
            return None
        if not isinstance(proof, dict):
            return None
        feedback = read_public(folder / "native-visible-feedback-and-cost/feedback.json",
                               proof.get("attempt"))
    return proof, feedback


def _source_record(run, event: dict, task: str) -> dict:
    head = event.get("head_sha")
    if not isinstance(head, str) or not SHA40.fullmatch(head):
        raise ValueError("ROUTE_DEFECT_SOURCE_SHA_MISSING")
    path = "pilot/worker_v08/native_tasks/" + task + ".json"
    obj = json.loads(run("git", "show", head + ":" + path))
    if (not isinstance(obj, dict) or not isinstance(obj.get("task_spec"), dict)):
        raise ValueError("ROUTE_DEFECT_ORIGINAL_REGISTRATION_INVALID")
    return obj


def inspect(run, api, repo: str, root: Path, event: dict):
    identity = _run_identity(event, repo)
    if identity is None or event.get("conclusion") != "failure":
        return None
    task, sha = identity
    try:
        issue_for_task(root, task)
    except ProjectConfigError:
        raise
    except ValueError:
        return None
    record = storage_path("registrations_root", root=root) / (task + ".json")
    if not record.is_file() or record.is_symlink():
        return None
    original = _source_record(run, event, task)
    if not any(cmd.get("argv", [None])[0] in ("python", "python3", "python3.12")
               for cmd in original["task_spec"].get("acceptance_commands", [])
               if isinstance(cmd, dict)):
        return None
    payload = _artifact_payload(run, api, repo, event)
    if payload is None:
        return None
    proof, feedback = payload
    request = issue_for_task(root, task)
    original_request = root / f"pilot/runs/req-{request}/proposal_requests/{task}.proposal-request.json"
    if original_request.is_symlink() or not original_request.is_file():
        return None
    envelope = json.loads(original_request.read_text("utf-8"))
    if (set(proof) != {"task_id", "attempt", "task_pack_sha256", "run_id"}
            or proof.get("task_id") != task or proof.get("run_id") != event["id"]
            or type(proof.get("attempt")) is not int
            or proof["attempt"] != feedback["attempt"]
            or proof.get("task_pack_sha256") != envelope.get("task_pack_sha256")
            or not classify(feedback, original)):
        return None
    return {"task": task, "sha": sha, "run_id": event["id"],
            "attempt": proof["attempt"], "request": request,
            "original": original, "legacy_pack": proof["task_pack_sha256"],
            "base": original["task_spec"]["base_head_sha"]}


def _comments(run, repo: str, number: int, api_list=None) -> list[dict]:
    """Use typed GitHub collection transport in production CP3.6."""
    if api_list is not None:
        return api_list(f"issues/{number}/comments")
    # Historical isolated T23 tests inject a command-based list response.
    result = json.loads(run("gh", "api",
        f"repos/{repo}/issues/{number}/comments?per_page=100"))
    if not isinstance(result, list) or len(result) >= 100:
        raise ValueError("ROUTE_DEFECT_COMMENT_HISTORY_INCOMPLETE")
    return result


def comment_defect(run, api, repo: str, evidence: dict,
                   api_list=None, *, allowed_task=None) -> str:
    task, sha = evidence["task"], evidence["sha"]
    number, run_id = evidence["request"], evidence["run_id"]
    marker = f"<!-- {MARKER}:{task}:{sha}:{run_id} -->"
    issue = api(f"issues/{number}")
    if (issue.get("number") != number or issue.get("pull_request")
            or "lf-request" not in {x.get("name") for x in issue.get("labels", [])
                                   if isinstance(x, dict)}):
        raise ValueError("ROUTE_DEFECT_ISSUE_UNVERIFIED")
    comments = _comments(run, repo, number, api_list)
    if not isinstance(comments, list) or len(comments) >= 100:
        raise ValueError("ROUTE_DEFECT_COMMENT_HISTORY_INCOMPLETE")
    if any(marker in str(c.get("body") or "") for c in comments
           if isinstance(c, dict)
           and (c.get("user") or {}).get("login") == "github-actions[bot]"):
        return "ROUTE_DEFECT_ALREADY_RECORDED"
    body = (marker + "\n**ROUTE_DEFECT confirmado:** el intento "
            + str(evidence["attempt"]) + "/3 de `" + task + "` (SHA `" + sha
            + "`) de la corrida " + str(run_id)
            + " no cuenta para el máximo de 3. "
            + "El fallo corresponde a una dependencia del comando Python de la ruta, "
            + "no a una evaluación válida del código propuesto. "
            + "La ruta preparará una corrección del registro y reintentará el mismo SHA "
            + "sin que el constructor reenvíe la propuesta.")
    if allowed_task is not None and not allowed_task(task):
        return "REQUEST_INACTIVE"
    run("gh", "issue", "comment", str(number), "--repo", repo, "--body", body)
    return "ROUTE_DEFECT_RECORDED"


def _export_fixed_pack(run, root: Path, task: str, spec: dict,
                       output: Path, base: str) -> str:
    import sys
    sys.path.insert(0, str(root / "pilot/worker_v08"))
    from export_task_pack import export
    with tempfile.TemporaryDirectory(prefix="t23-base-") as tmp:
        directory = Path(tmp)
        source = directory / "source"
        run("git", "worktree", "add", "--detach", str(source), base, cwd=root)
        try:
            task_path = directory / "task.json"
            task_path.write_bytes(canonical(spec))
            output.unlink()
            return export(source, task_path, output)
        finally:
            run("git", "worktree", "remove", "--force", str(source), cwd=root)


def prepare_repair(head, run, api, repo, root, evidence, worktree, draft,
                   pending_draft) -> dict:
    task, request = evidence["task"], "req-" + str(evidence["request"])
    registered = root / f"pilot/worker_v08/native_tasks/{task}.json"
    original = evidence["original"]
    current = json.loads(registered.read_text("utf-8"))
    fixed, count = convert(original)
    if current == fixed:
        return {"status": "ROUTE_DEFECT_REGISTRATION_ALREADY_FIXED", "task": task}
    if current != original or count == 0:
        raise ValueError("ROUTE_DEFECT_REGISTRATION_DRIFT")
    branch = f"lf/native-registration/route-python-{task}-{head[:12]}"
    prefix = f"lf/native-registration/route-python-{task}-"
    if pending_draft(prefix) or run("git", "ls-remote", "--heads", "origin", branch):
        return {"status": "ROUTE_DEFECT_REGISTRATION_PENDING", "task": task}
    original_pack = root / f"pilot/runs/{request}/proposal_requests/{task}.task-pack.json"
    if (original_pack.is_symlink() or not original_pack.is_file()
            or hashlib.sha256(original_pack.read_bytes()).hexdigest() != evidence["legacy_pack"]):
        raise ValueError("ROUTE_DEFECT_LEGACY_PACK_DRIFT")
    def create(checkout: Path):
        record_rel = f"pilot/worker_v08/native_tasks/{task}.json"
        pack_rel = f"pilot/runs/{request}/proposal_requests/{task}.task-pack.json"
        req_rel = f"pilot/runs/{request}/proposal_requests/{task}.proposal-request.json"
        migration_rel = f"pilot/worker_v08/route_migrations/{task}.json"
        target = checkout / record_rel
        target.write_bytes(canonical(fixed))
        pack = checkout / pack_rel
        current_pack = _export_fixed_pack(run, checkout, task, fixed["task_spec"],
                                          pack, evidence["base"])
        from pilot.orchestrator.native_submission_contract import enrich_request
        req = checkout / req_rel
        original_meta = json.loads(req.read_text("utf-8"))
        if original_meta.get("task_pack_sha256") != evidence["legacy_pack"]:
            raise ValueError("ROUTE_DEFECT_LEGACY_REQUEST_DRIFT")
        original_meta["task_pack_sha256"] = current_pack
        req.write_bytes(canonical(enrich_request(original_meta, fixed["task_spec"])))
        marker = migration(task, original, fixed, evidence["legacy_pack"],
                           current_pack, evidence["run_id"], evidence["sha"],
                           evidence["base"])
        dest = checkout / migration_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            raise ValueError("ROUTE_DEFECT_MIGRATION_ALREADY_EXISTS")
        dest.write_bytes(canonical(marker))
        paths = [record_rel, pack_rel, req_rel, migration_rel]
        review = draft(checkout, branch, request, paths,
                       "T23 route-only Python launcher repair; preserve lot, baseline, "
                       "holdout ref/hash and original proposal SHA; regenerate exact package",
                       f"route Python acceptance repair {task}")
        return {"status": "ROUTE_DEFECT_REGISTRATION_DRAFT", "task": task,
                "new_pack_sha256": current_pack, **review}
    return worktree(head, branch, create)


def comment_resubmit(run, api, repo: str, number: int, task: str,
                     sha: str, reason: str, api_list=None) -> str:
    marker = f"<!-- LF_NATIVE_ROUTE_RESUBMIT:{task}:{sha} -->"
    issue = api(f"issues/{number}")
    if issue.get("number") != number or "lf-request" not in {
            x.get("name") for x in issue.get("labels", []) if isinstance(x, dict)}:
        raise ValueError("ROUTE_DEFECT_ISSUE_UNVERIFIED")
    comments = _comments(run, repo, number, api_list)
    if any(marker in str(c.get("body") or "") for c in comments
           if isinstance(c, dict) and
           (c.get("user") or {}).get("login") == "github-actions[bot]"):
        return "ROUTE_DEFECT_RESUBMIT_ALREADY_NOTIFIED"
    msg = (marker + "\n**REENVÍO REQUERIDO:** `" + task + "` SHA `"
           + sha + "`: " + reason
           + ". Consulta el proposal-request.json actualizado en main y "
           + "vuelve a enviar un sobre con su task_pack_sha256 y base registrados.")
    run("gh", "issue", "comment", str(number), "--repo", repo, "--body", msg)
    return "ROUTE_DEFECT_RESUBMIT_NOTIFIED"


def replay_corrected(head, run, api, repo: str, root: Path,
                     rows: list[dict], api_list=None, allowed_task=None, format_decision=None) -> list[dict]:
    results = []
    done = set()
    for item in rows:
        if not isinstance(item, dict):
            continue
        match = RETRY_TITLE.fullmatch(item.get("display_title") or "")
        if match and item.get("event") == "workflow_dispatch":
            done.add((match.group(1), match.group(2)))
    migrations = root / "pilot/worker_v08/route_migrations"
    if not migrations.is_dir() or migrations.is_symlink():
        return []
    for file in sorted(migrations.glob("*.json")):
        task = file.stem
        try:
            live = allowed_task(task) if allowed_task is not None else True
        except RequestStateError:
            results.append({"task": task, "status": "BLOCKED",
                            "reason": "REQUEST_STATE_UNRESOLVED"})
            continue
        if not live:
            results.append({"task": task, "status": "REQUEST_CLOSED"})
            continue
        if not TASK.fullmatch(task):
            raise ValueError("ROUTE_DEFECT_MIGRATION_PATH_INVALID")
        reg = storage_path("registrations_root", root=root) / (task + ".json")
        if reg.is_symlink() or not reg.is_file():
            raise ValueError("ROUTE_DEFECT_REGISTRATION_MISSING")
        record = json.loads(reg.read_text("utf-8"))
        migration_info = verified_migration(root, task, record)
        if migration_info is None:
            raise ValueError("ROUTE_DEFECT_MIGRATION_DRIFT")
        sha = migration_info["proposal_commit_sha"]
        if (task, sha) in done:
            continue
        if format_decision is not None:
            state = format_decision(task, sha)
            if state != "CONTINUE":
                results.append({"task": task, "status": state, "proposal_sha": sha})
                continue
        source = api(f"actions/runs/{migration_info['source_run_id']}")
        if (_run_identity(source, repo) != (task, sha)
                or source.get("conclusion") != "failure"):
            raise ValueError("ROUTE_DEFECT_SOURCE_RUN_INVALID")
        request = issue_for_task(root, task)
        comment_defect(run, api, repo, {
            "request": request, "task": task, "sha": sha,
            "run_id": migration_info["source_run_id"], "attempt": 1,
        }, api_list, allowed_task=allowed_task)
        if allowed_task is not None and not allowed_task(task):
            continue
        branch = "lf/native-proposal/" + task
        remote = run("git", "ls-remote", "origin", "refs/heads/" + branch).split()
        if len(remote) != 2 or remote[0] != sha or remote[1] != "refs/heads/" + branch:
            results.append({"status": comment_resubmit(
                run, api, repo, request, task, sha,
                "la rama original ya no apunta al SHA enviado", api_list)})
            continue
        run("git", "fetch", "--no-tags", "origin", sha)
        try:
            validate_proposal_only(root, sha, main_sha=head, branch=branch,
                                   allow_historical_base=True)
            envelope = json.loads(run("git", "show",
                                      sha + ":pilot/native_proposals/" + task + ".json"))
        except (ProposalPushBlocked, ValueError):
            results.append({"status": comment_resubmit(
                run, api, repo, request, task, sha,
                "el sobre original ya no supera la validación de procedencia", api_list)})
            continue
        if (not isinstance(envelope, dict)
                or set(envelope) != {"task_pack_sha256", "proposal_sha256", "proposal", "author"}
                or envelope.get("author") != "GPT_NATIVE"
                or not isinstance(envelope.get("proposal"), dict)
                or hashlib.sha256(json.dumps(
                    envelope["proposal"], sort_keys=True, separators=(",", ":"),
                    ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
                       != envelope.get("proposal_sha256")
                or envelope.get("task_pack_sha256") != migration_info["legacy_task_pack_sha256"]):
            results.append({"status": comment_resubmit(
                run, api, repo, request, task, sha,
                "el SHA del paquete original difiere del paquete histórico certificado", api_list)})
            continue
        if allowed_task is not None and not allowed_task(task):
            continue
        run("gh", "workflow", "run", "worker-native.yml", "--repo", repo, "--ref", "main",
            "-f", "task=" + task, "-f", "proposal_commit_sha=" + sha,
            "-f", "attempt=1", "-f", "route_retry=true")
        results.append({"status": "ROUTE_DEFECT_REEVALUATION_DISPATCHED",
                        "task": task, "proposal_sha": sha,
                        "source_run_id": migration_info["source_run_id"]})
    return results


def sweep(head, run, api, repo, root, worktree, draft, pending_draft,
          api_list=None, allowed_task=None, format_decision=None):
    rows = history(api)
    results = []
    # A historical run is classified once from trusted visible artifacts; no
    # source file is changed by this classification alone.
    scheduled = False
    for item in rows:
        if not isinstance(item, dict) or item.get("conclusion") != "failure":
            continue
        if _run_identity(item, repo) is None:
            continue
        evidence = inspect(run, api, repo, root, item)
        if evidence is None:
            continue
        try:
            live = allowed_task(evidence["task"]) if allowed_task is not None else True
        except RequestStateError:
            results.append({"task": evidence["task"], "status": "BLOCKED",
                            "reason": "REQUEST_STATE_UNRESOLVED"})
            continue
        if not live:
            results.append({"task": evidence["task"], "status": "REQUEST_CLOSED"})
            continue
        results.append({"status": comment_defect(run, api, repo, evidence,
                                                   api_list, allowed_task=allowed_task),
                        "task": evidence["task"], "run_id": item["id"]})
        # One generated CHG / Draft per sweep; subsequent tasks follow after
        # Train advances main, avoiding two bot branches claiming one CHG.
        if not scheduled and (allowed_task is None or allowed_task(evidence["task"])):
            registration = prepare_repair(head, run, api, repo, root,
                                          evidence, worktree, draft, pending_draft)
            results.append(registration)
            if registration["status"] in (
                    "ROUTE_DEFECT_REGISTRATION_DRAFT",
                    "ROUTE_DEFECT_REGISTRATION_PENDING"):
                scheduled = True
    results.extend(replay_corrected(head, run, api, repo, root, rows,
                                    api_list, allowed_task=allowed_task, format_decision=format_decision))
    return results
