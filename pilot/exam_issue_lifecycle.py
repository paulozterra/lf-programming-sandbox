"""Close exam-request only after verified Train registration merge, idempotently."""
from __future__ import annotations

import json
from pathlib import Path
import re


class LifecycleBlocked(ValueError):
    pass


def registration_task(branch: str) -> str | None:
    m = re.fullmatch(r"lf/native-registration/([a-z][a-z0-9_-]{0,31})-[0-9a-f]{12}", branch)
    return m.group(1) if m else None


def issue_for(api, task: str, slug: str) -> dict | None:
    issues = api.call("GET", "/issues?state=open&labels=exam-request&per_page=100")
    if not isinstance(issues, list) or len(issues) >= 100:
        raise LifecycleBlocked("EXAM_REQUEST_UNVERIFIED")
    matches = [issue for issue in issues if isinstance(issue, dict)
               and issue.get("state") == "open"
               and issue.get("title") == f"EXAM_REQUEST: {task}"
               and any(row.get("name") == "exam-request"
                       for row in issue.get("labels", []))
               and f"- Pedido: \`{slug}\`" in issue.get("body", "")
               and f"- Task ID: \`{task}\`" in issue.get("body", "")]
    if len(matches) > 1:
        raise LifecycleBlocked("EXAM_REQUEST_DUPLICATE")
    return matches[0] if matches else None


def close_registered(api, sha: str, branch: str, git, root: Path) -> str:
    task = registration_task(branch)
    if task is None:
        return "NO_EXAM_REGISTRATION"
    from pilot.train_handoff import merged_request_slug
    # Verify trusted first-parent merger delta; no issue may be closed merely
    # because a branch was named native-registration.
    changes = set(git("diff", "--name-only", sha + "^1", sha).splitlines())
    registered = f"pilot/worker_v08/native_tasks/{task}.json"
    if registered not in changes:
        raise LifecycleBlocked("EXAM_REGISTRATION_NOT_MERGED")
    paths = list((root / "pilot/runs").glob("req-*/chain_plan.json"))
    scopes = []
    for plan in paths:
        if plan.is_symlink() or plan.parent.is_symlink():
            raise LifecycleBlocked("EXAM_PLAN_PATH_INVALID")
        obj = json.loads(plan.read_text("utf-8"))
        if any(item.get("task_name") == task for item in obj.get("bindings", [])):
            scopes.append(plan.parent.name)
    if len(scopes) != 1:
        raise LifecycleBlocked("EXAM_REQUEST_SCOPE_UNRESOLVED")
    slug = scopes[0]
    issue = issue_for(api, task, slug)
    if issue is None:
        return "EXAM_ISSUE_ALREADY_CLOSED_OR_ABSENT"
    number = issue.get("number")
    if type(number) is not int:
        raise LifecycleBlocked("EXAM_REQUEST_UNVERIFIED")
    comment = (f"Examen integrado: tarea \`{task}\` registrada en main "
               f"mediante Train, commit \`{sha}\`. "
               "La cadena continúa según dependencias y verificación de CI.")
    api.call("POST", f"/issues/{number}/comments", {"body": comment})
    api.call("PATCH", f"/issues/{number}", {"state": "closed",
                                            "state_reason": "completed"})
    return "EXAM_ISSUE_CLOSED"
