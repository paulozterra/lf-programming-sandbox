"""Central, fail-closed lifecycle decision for request-bound automation.

Synthetic or legacy identifiers must be deliberately enrolled in a versioned
allowlist. Closed GitHub issues are never active, independently of state_reason.
"""
from __future__ import annotations

# Resolve the trusted repository package for direct script execution.
import sys as _project_sys
from pathlib import Path as _project_Path
_project_sys.path.insert(0, str(_project_Path(__file__).resolve().parents[2]))

import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from pilot.orchestrator.request_finalize import verified_chain_complete
from pilot.config.project_config import ProjectConfigError, storage, storage_path, template_path_pattern, repo_storage

ROOT = Path(__file__).resolve().parents[2]
REQUEST = re.compile(r"req-([1-9][0-9]*)\Z")
ALLOWLIST = ROOT / "pilot/orchestrator/request_lifecycle_allowlist.json"
OPEN = "OPEN"
SUSPENDING = "SUSPENDING"
SUSPENDED = "SUSPENDED"
CONTROL_PATH = "pilot/orchestrator/request_lifecycle_control.json"
CONTROL_SCHEMA = "LF_REQUEST_LIFECYCLE_CONTROL_V1"
CONTROL_STATES = {SUSPENDING, SUSPENDED, "ACTIVE"}
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
CLOSED_FINALIZED = "CLOSED_FINALIZED"
CLOSED_CANCELLED = "CLOSED_CANCELLED"
CODE = "REQUEST_STATE_UNRESOLVED"


class RequestStateError(ValueError):
    """Machine-readable state failure; must not authorize side effects."""


def unresolved():
    raise RequestStateError(CODE)


def _synthetic_allowed(request: str, allowlist: Path) -> bool:
    try:
        if allowlist.is_symlink() or not allowlist.is_file():
            unresolved()
        data = json.loads(allowlist.read_text(encoding="utf-8"))
        values = data["allowed_non_issue_requests"]
        if (not isinstance(values, list) or len(values) != len(set(values))
                or not all(isinstance(v, str) and re.fullmatch(
                    r"[a-z][a-z0-9_-]{0,63}", v) and not REQUEST.fullmatch(v)
                    for v in values)):
            unresolved()
        return request in values
    except (OSError, ValueError, TypeError, KeyError):
        unresolved()


def _finalized(request: str, root: Path) -> bool:
    """Use the canonical finalization proof, never a second implementation."""
    folder = storage_path("requests_root", request, root=root)
    return verified_chain_complete(folder, root=root)



def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            unresolved()
        result[key] = value
    return result


def parse_control(raw: bytes) -> dict:
    """Strict, versioned authorization ledger. No implicit reset by deletion."""
    try:
        if not isinstance(raw, bytes) or not 0 < len(raw) <= 65536:
            unresolved()
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_strict_object)
        if (not isinstance(value, dict) or set(value) != {"schema_version", "requests"}
                or value["schema_version"] != CONTROL_SCHEMA
                or not isinstance(value["requests"], dict)):
            unresolved()
        for slug, entry in value["requests"].items():
            if (not REQUEST.fullmatch(slug) or not isinstance(entry, dict)
                    or set(entry) != {"state", "authorization_pr"}
                    or entry["state"] not in CONTROL_STATES
                    or type(entry["authorization_pr"]) is not int
                    or entry["authorization_pr"] <= 0):
                unresolved()
        return value["requests"]
    except (ValueError, TypeError, KeyError, UnicodeError):
        unresolved()


def read_control(api, revision="main") -> dict:
    """Read current trusted main via GitHub, not a possibly stale job checkout."""
    if revision != "main" and (not isinstance(revision, str) or not SHA40.fullmatch(revision)):
        unresolved()
    try:
        item = api(f"contents/{CONTROL_PATH}?ref={revision}")
        if (not isinstance(item, dict) or item.get("type") != "file"
                or item.get("encoding") != "base64"
                or type(item.get("size")) is not int or not 0 < item["size"] <= 65536
                or not isinstance(item.get("content"), str)):
            unresolved()
        raw = base64.b64decode("".join(item["content"].splitlines()), validate=True)
        if len(raw) != item["size"]:
            unresolved()
        return parse_control(raw)
    except Exception as exc:
        raise RequestStateError(CODE) from exc


def control_state(request: str, api) -> str:
    """An enrolled request needs a real merged PR and an exact historical entry."""
    entries = read_control(api)
    entry = entries.get(request)
    if entry is None:
        return OPEN
    try:
        number = entry["authorization_pr"]
        pr = api(f"pulls/{number}")
        merge = pr.get("merge_commit_sha")
        base, head = pr.get("base", {}), pr.get("head", {})
        repo = base.get("repo", {}).get("full_name")
        if (pr.get("number") != number or pr.get("merged") is not True
                or base.get("ref") != "main" or not repo
                or head.get("repo", {}).get("full_name") != repo
                or not isinstance(merge, str) or not SHA40.fullmatch(merge)):
            unresolved()
        if read_control(api, merge).get(request) != entry:
            unresolved()
        # The merge commit binds the approved head and the exact predecessor.
        commit = api(f"commits/{merge}")
        parents = commit.get("parents", [])
        if (commit.get("sha") != merge or len(parents) != 2
                or any(not SHA40.fullmatch(p.get("sha", "")) for p in parents)
                or head.get("sha") != parents[1]["sha"]):
            unresolved()
        if (commit.get("commit", {}).get("message", "").splitlines()[:1]
                != [f"Merge PR #{number} via sandbox-train"]):
            unresolved()
        previous = read_control(api, parents[0]["sha"])
        historical = read_control(api, merge)
        if validate_control_transition(previous, historical, number) != request:
            unresolved()
        verify_owner_transition(api, pr, request,
                                previous.get(request, {}).get("state", "ACTIVE"),
                                entry["state"])
        if read_control(api).get(request) != entry:
            unresolved()
        return OPEN if entry["state"] == "ACTIVE" else entry["state"]
    except Exception as exc:
        raise RequestStateError(CODE) from exc


def verify_owner_label(api, number: int, owner: str) -> None:
    """Only a fresh owner label, not a bot label or a PR description."""
    latest = None
    try:
        for page in range(1, 11):
            rows = api(f"issues/{number}/events?per_page=100&page={page}")
            if not isinstance(rows, list) or len(rows) > 100:
                unresolved()
            for row in rows:
                if not isinstance(row, dict):
                    unresolved()
                if (row.get("event") in ("labeled", "unlabeled")
                        and (row.get("label") or {}).get("name") == "ready-to-merge"):
                    latest = row
            if len(rows) < 100:
                break
        else:
            unresolved()
        if (latest is None or latest.get("event") != "labeled"
                or (latest.get("actor") or {}).get("login") != owner):
            unresolved()
    except Exception as exc:
        raise RequestStateError(CODE) from exc


def _stamp(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value):
        unresolved()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        unresolved()


def _paged(api, path, field=None):
    """Bounded complete collection, no authorization on truncation or duplicate IDs."""
    rows, seen = [], set()
    for page in range(1, 11):
        data = api(path + ("&" if "?" in path else "?") + f"per_page=100&page={page}")
        total = data.get("total_count") if field and isinstance(data, dict) else None
        batch = data.get(field) if field and isinstance(data, dict) else data
        if not isinstance(batch, list) or len(batch) > 100:
            unresolved()
        for row in batch:
            if not isinstance(row, dict) or type(row.get("id")) is not int or row["id"] in seen:
                unresolved()
            seen.add(row["id"])
            rows.append(row)
        if len(batch) < 100:
            if field and (type(total) is not int or total != len(rows)):
                unresolved()
            return rows
    unresolved()


def transition_marker(request, old, new, head):
    marker = f"LF_LIFECYCLE_AUTHORIZE {request} {old}->{new} {head}"
    if new == SUSPENDED:
        marker += "\nDRAIN_CONFIRMED: external examiner sessions drained; no legacy replays authorized"
    return marker


def verify_owner_transition(api, pr, request, old, new):
    """A ready label alone cannot authorize a different HEAD or transition.
    An owner COMMENT review is permitted even on their own PR; no fake approval.
    """
    try:
        number = pr["number"]
        head = pr["head"]["sha"]
        repo = pr["base"]["repo"]["full_name"]
        if (not SHA40.fullmatch(head) or not isinstance(repo, str)
                or pr["base"]["ref"] != "main" or pr["head"]["repo"]["full_name"] != repo):
            unresolved()
        owner = repo.split("/")[0]
        verify_owner_label(api, number, owner)
        marker = transition_marker(request, old, new, head)
        reviews = _paged(api, f"pulls/{number}/reviews")
        cutoff = _stamp(pr["merged_at"]) if pr.get("merged") else datetime.now(timezone.utc)
        matches = [row for row in reviews if (row.get("user") or {}).get("login") == owner
                   and row.get("state") in ("COMMENTED", "APPROVED")
                   and row.get("commit_id") == head and row.get("body", "").strip() == marker
                   and _stamp(row.get("submitted_at")) <= cutoff]
        if not matches:
            unresolved()
    except Exception as exc:
        raise RequestStateError(CODE) from exc


# Only jobs that can change a request, including upstream dispatchers.
DRAIN_WORKFLOWS = frozenset({
    "worker-native.yml", "worker-native-trigger.yml", "worker-pilot.yml",
    "exam-rehearsal.yml", "native-verified-integration.yml", "chain-lots.yml",
    "pg37-evidence.yml", "auto-integrate.yml", "sandbox-train.yml",
    "train-handoff.yml", "request-intake.yml", "request-finalize.yml",
    "request-failure-watchdog.yml", "t7-request.yml", "r1-reconcile.yml",
})


def verify_drain(api, request, previous, *, current_train_id=None):
    """SUSPENDED is a second transition, never inferred from the first label.
    Conservatively drain ambiguous/old route jobs, plus examiner reservations.
    The owner review separately attests external examiner sessions are drained.
    No cancellation, rerun or other write is performed here.
    """
    try:
        if previous.get("state") != SUSPENDING or control_state(request, api) != SUSPENDING:
            unresolved()
        prior = api(f"pulls/{previous['authorization_pr']}")
        cutoff = _stamp(prior["merged_at"])
        merge = prior.get("merge_commit_sha")
        if not isinstance(merge, str) or not SHA40.fullmatch(merge):
            unresolved()
        for status in ("queued", "in_progress", "waiting", "pending", "requested", "action_required"):
            for run in _paged(api, f"actions/runs?status={status}", "workflow_runs"):
                path = run.get("path", "")
                if not isinstance(path, str) or not path:
                    unresolved()
                workflow = path.split("@", 1)[0].rsplit("/", 1)[-1]
                if workflow not in DRAIN_WORKFLOWS:
                    continue
                # The serial Train performing this exact transition is not a
                # competing request executor. Never exempt another run.
                if (workflow == "sandbox-train.yml" and run["id"] == current_train_id
                        and run.get("status") == "in_progress" and run.get("run_attempt") == 1):
                    continue
                # New trusted-main first attempts see SUSPENDING. Older runs,
                # replays and ambiguous branch snapshots must drain first.
                if (_stamp(run.get("created_at")) <= cutoff
                        or run.get("run_attempt") != 1 or run.get("head_branch") != "main"):
                    raise RequestStateError("REQUEST_DRAIN_PENDING")
                sha = run.get("head_sha")
                if not isinstance(sha, str) or not SHA40.fullmatch(sha):
                    unresolved()
                relation = api(f"compare/{merge}...{sha}")
                if (relation.get("status") not in ("ahead", "identical")
                        or (relation.get("base_commit") or {}).get("sha") != merge
                        or (relation.get("merge_base_commit") or {}).get("sha") != merge):
                    raise RequestStateError("REQUEST_DRAIN_PENDING")
        for issue in _paged(api, "issues?state=open&labels=examiner-working"):
            body = issue.get("body")
            if not isinstance(body, str):
                unresolved()
            slugs = set(re.findall(r"(?m)^- Pedido: `(req-[1-9][0-9]*)`\s*$", body))
            if len(slugs) != 1:
                unresolved()
            if request in slugs:
                raise RequestStateError("REQUEST_DRAIN_PENDING")
        if read_control(api).get(request) != previous:
            unresolved()
    except RequestStateError:
        raise
    except Exception as exc:
        raise RequestStateError(CODE) from exc


def validate_control_transition(previous: dict, current: dict, number: int) -> str:
    """The Train must use this before integrating any subsequent policy PR.
    SUSPENDING denies admission while old jobs drain; only then may the owner
    authorize SUSPENDED. ACTIVE is explicit and never implied by deletion.
    """
    if (type(number) is not int or number <= 0
            or any(slug not in current for slug in previous)):
        unresolved()
    changed = [slug for slug, entry in current.items() if previous.get(slug) != entry]
    if len(changed) != 1:
        unresolved()
    slug = changed[0]
    old = previous.get(slug, {}).get("state", "ACTIVE")
    new = current[slug]
    permitted = {"ACTIVE": SUSPENDING, SUSPENDING: SUSPENDED, SUSPENDED: "ACTIVE"}
    if new["state"] != permitted.get(old) or new["authorization_pr"] != number:
        unresolved()
    return slug


def inactive_reason(state: str) -> str:
    if state in (SUSPENDING, SUSPENDED):
        return "REQUEST_SUSPENDED"
    if state in (CLOSED_FINALIZED, CLOSED_CANCELLED):
        return "REQUEST_CLOSED"
    unresolved()


def request_state(request: str, api, *, root: Path = ROOT,
                  allowlist: Path | None = None) -> str:
    """Freshly resolve a GitHub issue before each external effect boundary."""
    if not isinstance(request, str):
        unresolved()
    match = REQUEST.fullmatch(request)
    if match is None:
        if _synthetic_allowed(request, allowlist or ALLOWLIST):
            return OPEN
        unresolved()
    number = int(match.group(1))
    try:
        item = api("issues/" + str(number))
    except Exception as exc:
        raise RequestStateError(CODE) from exc
    if (not isinstance(item, dict) or type(item.get("number")) is not int
            or item["number"] != number or item.get("pull_request")
            or item.get("state") not in ("open", "closed")):
        unresolved()
    if item["state"] == "open":
        return control_state(request, api)
    return CLOSED_FINALIZED if _finalized(request, root) else CLOSED_CANCELLED


def require_open(request: str, api, *, root: Path = ROOT) -> None:
    state = request_state(request, api, root=root)
    if state != OPEN:
        raise RequestStateError(inactive_reason(state))


def require_finalized_audit(request: str, api, *, root: Path = ROOT) -> None:
    """Historical audit only: a closed proof never overrides suspension."""
    if not isinstance(request, str) or not REQUEST.fullmatch(request):
        unresolved()
    state = request_state(request, api, root=root)
    if state in (SUSPENDING, SUSPENDED):
        raise RequestStateError("REQUEST_SUSPENDED")
    if state != CLOSED_FINALIZED:
        raise RequestStateError("AUDIT_REQUEST_NOT_FINALIZED")
    if control_state(request, api) != OPEN:
        raise RequestStateError("REQUEST_SUSPENDED")


def request_for_task(task: str, *, root: Path = ROOT, registered: bool = True) -> str:
    """Resolve a task against unique, trusted main chain plans; never proposal data.

    Both historical and per-request plans are supported. Duplicate copies for
    the same request must match byte-for-byte. Zero or multiple owners deny.
    """
    if not isinstance(task, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", task):
        unresolved()
    registration = storage_path("registrations_root", task + ".json", root=root)
    if registration.is_symlink() or (registered and not registration.is_file()):
        unresolved()
    from pilot.orchestrator.lot_recovery import for_successor
    sources: dict[str, Path] = {}
    try:
        folders = [
            (p.stem, p) for p in sorted((storage_path("chain_plans_root", root=root)).glob("*.json"))
        ] + [
            (p.parent.name, p) for p in sorted((storage_path("requests_root", root=root)).glob("*/chain_plan.json"))
        ]
        for request, path in folders:
            if (path.is_symlink() or path.parent.is_symlink()
                    or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", request)):
                unresolved()
            if request in sources:
                if sources[request].read_bytes() != path.read_bytes():
                    unresolved()
                continue
            sources[request] = path
        continuation = for_successor(root, task)
        owners = []
        for request, path in sources.items():
            obj = json.loads(path.read_text(encoding="utf-8"))
            bindings = obj["bindings"]
            if (not isinstance(obj, dict) or obj.get("request_id") != request
                    or not isinstance(bindings, list)):
                unresolved()
            bound_task = (continuation["original_task"] if continuation and
                          continuation["request_id"] == request else task)
            hits = [entry for entry in bindings if isinstance(entry, dict)
                    and entry.get("task_name") == bound_task]
            if continuation and hits:
                if (request != continuation["request_id"] or
                        hits[0].get("lot_id") != continuation["lot_id"]):
                    unresolved()
            if len(hits) > 1:
                unresolved()
            if hits:
                entry = hits[0]
                if (not isinstance(entry.get("lot_id"), str)
                        or not isinstance(entry.get("template_path"), str)
                        or not entry["template_path"].startswith(repo_storage()["requests_root"] + "/" + request + "/")):
                    unresolved()
                owners.append(request)
        if len(owners) != 1:
            unresolved()
        return owners[0]
    except ProjectConfigError:
        raise
    except (OSError, ValueError, TypeError, KeyError, UnicodeError) as exc:
        raise RequestStateError(CODE) from exc


def github_issue_api(path: str):
    """Read GitHub state with the trusted job token, never an input-provided token."""
    import os
    import subprocess
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo or not re.fullmatch(r"[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+", repo):
        unresolved()
    result = subprocess.run(
        ["gh", "api", "repos/" + repo + "/" + path],
        env={**os.environ, "GH_TOKEN": token},
        capture_output=True, text=True, timeout=30, check=True)
    response = json.loads(result.stdout)
    if not isinstance(response, (dict, list)):
        unresolved()
    return response


def require_task_open(task: str, *, root: Path = ROOT, api=None) -> str:
    """Typed fail-closed gate shared by Worker and CP3.5."""
    request = request_for_task(task, root=root)
    require_open(request, api or github_issue_api, root=root)
    return request


def request_ids_for_pr(branch: str, paths: list[str], *, root: Path = ROOT) -> set[str]:
    """Resolve affected requests from trusted plan bindings and exact route paths.
    General infrastructure PRs and the historical global registry are not a
    request continuation. The caller must supply the complete file list.
    """
    from pilot.native_registration_family import registration_family

    if not isinstance(branch, str) or not isinstance(paths, list) or not all(
            isinstance(p, str) for p in paths):
        unresolved()
    requests = {m.group(1) for path in paths if
                (m := re.match(r"pilot/runs/(req-[1-9][0-9]*)/", path))}
    requests.update(m.group(1) for path in paths if
                    (m := re.fullmatch(r"pilot/orchestrator/chain_plans/(req-[1-9][0-9]*)[.]json", path)))
    requests.update(m.group(1) for path in paths if
                    (m := re.match(r"pilot/orchestrator/evidence_inputs/(req-[1-9][0-9]*)/", path)))
    for path in paths:
        m = re.fullmatch(r"pilot/(?:worker_v08/(?:native_tasks|route_migrations)|native_proposals)/([a-z][a-z0-9_-]{0,31})[.]json", path)
        if m is None:
            m = re.fullmatch(r"pilot/holdouts/([a-z][a-z0-9_-]{0,31})[.](?:oracle|reference)[.]json[.]age", path)
        if m is None:
            m = re.fullmatch(r"pilot/worker_v08/(?:examiner_defects|intake_defects|route_tool_defects)/([a-z][a-z0-9_-]{0,31})(?:/[1-9][0-9]*)?[.]json", path)
        if m is None:
            m = re.match(r"[.]lf/worker-context/([a-z][a-z0-9_-]{0,31})/", path)
        if m:
            requests.add(request_for_task(m.group(1), root=root, registered=False))
    task = None
    if branch.startswith("lf/native-registration/"):
        family, task = registration_family(branch)
        if family not in ("registration", "auxiliary") or task is None:
            unresolved()
    else:
        for pattern in (
                r"lf/native-integration/([a-z][a-z0-9_-]{0,31})-run-[1-9][0-9]*",
                r"lf/exam-retire/([a-z][a-z0-9_-]{0,31})-[0-9a-f]{12}",
                r"(?:lf/)?exam/([a-z][a-z0-9_-]{0,31})"):
            match = re.fullmatch(pattern, branch)
            if match:
                task = match.group(1)
                break
    if task:
        owner = request_for_task(task, root=root, registered=False)
        if requests and requests != {owner}:
            unresolved()
        requests.add(owner)
    elif branch.startswith(("lf/native-integration/", "lf/exam-retire/", "exam/", "lf/exam/")):
        unresolved()
    direct = re.fullmatch(r"lf/request/(req-[1-9][0-9]*)", branch)
    generated = re.fullmatch(r"lf/(?:chain-complete|chain-blocked|evidence)/(req-[1-9][0-9]*)-[0-9a-f]{12}", branch)
    if direct or generated:
        owner = (direct or generated).group(1)
        if requests and requests != {owner}:
            unresolved()
        requests.add(owner)
    if branch.startswith("lf/generated-t7/") and not requests:
        unresolved()
    return requests


def require_pr_open(branch: str, paths: list[str], api, *, root: Path = ROOT, pr=None):
    # Historical audit is a separate, tightly scoped circuit. Check even when
    # the suspension ledger is empty; a mixed PR cannot acquire this exception.
    from pilot.audit.audit_lifecycle import is_audit_scope, require_audit_pr
    if is_audit_scope(branch, paths):
        if not isinstance(pr, dict) or pr.get("head", {}).get("ref") != branch:
            unresolved()
        require_audit_pr(pr, api, root=root, expected_paths=paths)
        return
    control = read_control(api)
    # Global historical registry is not a new implementation or admission.
    # It may record merges that occurred before suspension; no other paths
    # may travel under this branch family.
    if branch.startswith("lf/implemented-registry/"):
        if (not re.fullmatch(r"lf/implemented-registry/[0-9a-f]{12}", branch)
                or paths != ["pilot/registry/implemented.json"]):
            unresolved()
        return
    if "pilot/registry/implemented.json" in paths:
        unresolved()
    if not control:
        return
    for slug in sorted(request_ids_for_pr(branch, paths, root=root)):
        if slug in control:
            require_open(slug, api, root=root)


def main():
    """Live admission check for request-bound workflow steps."""
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    args = parser.parse_args()
    try:
        require_open(args.request, github_issue_api)
    except RequestStateError as exc:
        print(str(exc))
        raise SystemExit(1) from exc
    print("REQUEST_OPEN")


if __name__ == "__main__":
    main()
