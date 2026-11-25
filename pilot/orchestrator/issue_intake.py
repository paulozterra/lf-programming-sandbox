#!/usr/bin/env python3
"""T9: privileged issue intake and independent exact-byte verification.

Only trusted main runs this code. Issue bodies are data, never shell commands.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.error
import urllib.request

REPO = "paulozterra/lf-programming-sandbox"
BOT = "github-actions[bot]"
SLUG = re.compile(r"req-[1-9][0-9]*\Z")
FIELD = "### Pedido"
ERROR = "PEDIDO_AUTOR_NO_AUTORIZADO"


class Blocked(ValueError):
    pass


def request_text(body: str) -> str:
    """Extract the exact value emitted by GitHub Issue Forms, no trimming."""
    if not isinstance(body, str):
        raise Blocked("PEDIDO_VACIO")
    if not body.startswith(FIELD + "\n"):
        raise Blocked("PEDIDO_FORMULARIO_INVALIDO")
    value = body[len(FIELD) + 1:]
    # GitHub Issue Forms render an empty line after a heading.
    if value.startswith("\n"):
        value = value[1:]
    # Ignore only GitHub's structural field boundary; never normalize user text.
    if "\n### " in value:
        raise Blocked("PEDIDO_FORMULARIO_INVALIDO")
    if not value.strip():
        raise Blocked("PEDIDO_VACIO")
    return value


def metadata(issue: dict) -> dict:
    number = issue.get("number")
    author = issue.get("user", {}).get("login")
    date = issue.get("created_at")
    if type(number) is not int or number < 1 or not isinstance(author, str) or not author:
        raise Blocked("PEDIDO_ISSUE_INVALIDO")
    if not isinstance(date, str) or not re.fullmatch(
        r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", date
    ):
        raise Blocked("PEDIDO_FECHA_INVALIDA")
    return {"issue": number, "author": author, "date": date}


def allowed_permission(level: str) -> bool:
    return level in ("admin", "maintain", "write")


def expected_files(issue: dict) -> dict[str, bytes]:
    info = metadata(issue)
    slug = f"req-{info['issue']}"
    if not SLUG.fullmatch(slug):
        raise Blocked("PEDIDO_SLUG_INVALIDO")
    root = f"pilot/runs/{slug}/"
    return {
        root + "request.md": request_text(issue.get("body")).encode("utf-8"),
        root + "request_meta.json": (
            json.dumps(info, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        ).encode("utf-8"),
    }


class API:
    def __init__(self, token: str):
        if not token:
            raise Blocked("PEDIDO_TOKEN_AUSENTE")
        self.token = token

    def call(self, method: str, path: str, payload=None):
        if not path.startswith("/") or ".." in path or "//" in path:
            raise Blocked("PEDIDO_API_PATH_INVALIDO")
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            "https://api.github.com/repos/" + REPO + path,
            data=data, method=method,
            headers={"Authorization": "Bearer " + self.token,
                     "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28",
                     "Content-Type": "application/json",
                     "User-Agent": "LF-request-intake"})
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                raw = response.read(1_000_001)
            if len(raw) > 1_000_000:
                raise Blocked("PEDIDO_API_OVERSIZE")
            return json.loads(raw) if raw else {}
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            raise Blocked("PEDIDO_API_FAILED") from exc

    def issue(self, number: int) -> dict:
        return self.call("GET", f"/issues/{number}")

    def permission(self, author: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9-]{1,39}", author):
            raise Blocked(ERROR)
        try:
            result = self.call("GET", f"/collaborators/{author}/permission")
        except Blocked:
            # Unknown and external accounts cannot obtain a collaborator privilege.
            return ""
        return result.get("permission", "")

    def content_bytes(self, path: str, sha: str) -> bytes:
        result = self.call("GET", f"/contents/{path}?ref={sha}")
        if result.get("encoding") != "base64" or result.get("type") != "file":
            raise Blocked("PEDIDO_CONTENIDO_INVALIDO")
        try:
            value = base64.b64decode("".join(result["content"].split()), validate=True)
        except (KeyError, ValueError) as exc:
            raise Blocked("PEDIDO_CONTENIDO_INVALIDO") from exc
        if len(value) != result.get("size"):
            raise Blocked("PEDIDO_CONTENIDO_INVALIDO")
        return value

    def comment(self, number: int, message: str):
        self.call("POST", f"/issues/{number}/comments", {"body": message})


def verify(api: API, number: int, sha: str, paths: list[str]) -> None:
    issue = api.issue(number)
    if not allowed_permission(api.permission(metadata(issue)["author"])):
        raise Blocked(ERROR)
    expected = expected_files(issue)
    if sorted(paths) != sorted(expected):
        raise Blocked("PEDIDO_RUTAS_INVALIDAS")
    for path, value in expected.items():
        if api.content_bytes(path, sha) != value:
            raise Blocked("PEDIDO_CONTENIDO_MODIFICADO")


def git(*args):
    subprocess.run(["git", *args], check=True)


REJECTION_GUIDANCE = {
    "PEDIDO_FORMULARIO_INVALIDO": "Usa la plantilla Nuevo pedido con un único campo ### Pedido.",
    "PEDIDO_VACIO": "Completa el campo Pedido con la solicitud.",
    "PEDIDO_FECHA_INVALIDA": "Solicita al responsable revisar la fecha del issue.",
    "PEDIDO_EVENTO_NO_COINCIDE": "Solicita al responsable revisar los datos del evento.",
    "PEDIDO_YA_EXISTE": "Solicita al responsable revisar el registro existente.",
}


def notify_rejection(api: API, number: int, code: str) -> None:
    if type(number) is not int or number < 1:
        return
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{3,100}", code):
        return
    marker = f"<!-- lf-t9-rejection:{code} -->"
    try:
        for page in range(1, 11):
            rows = api.call("GET", f"/issues/{number}/comments?per_page=100&page={page}")
            if not isinstance(rows, list) or len(rows) > 100:
                raise ValueError("PEDIDO_COMMENT_HISTORY_INVALID")
            for row in rows:
                user, body = row.get("user"), row.get("body")
                if not isinstance(user, dict) or not isinstance(body, str):
                    raise ValueError("PEDIDO_COMMENT_HISTORY_INVALID")
                if user.get("login") == BOT and marker in body.splitlines():
                    return
            if len(rows) < 100:
                break
        else:
            raise ValueError("PEDIDO_COMMENT_HISTORY_INCOMPLETE")
        guidance = REJECTION_GUIDANCE.get(
            code, "Solicita al responsable de T9 revisar este código antes de reintentar.")
        api.comment(number, f"{marker}\n{code}\n{guidance}")
    except Exception:
        print(f"T9_COMMENT_FAILED {code}", file=sys.stderr, flush=True)


def intake(api: API, event: dict):
    try:
        return _intake(api, event)
    except Blocked as exc:
        issue = event.get("issue")
        if isinstance(issue, dict):
            notify_rejection(api, issue.get("number"), str(exc))
        raise


def _intake(api: API, event: dict):
    issue_event = event.get("issue", {})
    info = metadata(issue_event)
    issue = api.issue(info["issue"])
    if metadata(issue) != info:
        raise Blocked("PEDIDO_EVENTO_NO_COINCIDE")
    if not allowed_permission(api.permission(info["author"])):
        api.comment(info["issue"], ERROR)
        return ERROR
    files = expected_files(issue)
    slug = f"req-{info['issue']}"
    branch = f"lf/request/{slug}"
    # Same issue may get opened and labeled events; never create two PRs.
    existing = api.call("GET", f"/pulls?state=all&head=paulozterra:{branch}&per_page=100")
    if existing:
        return "PEDIDO_YA_REGISTRADO"
    if any(isinstance(label, dict) and label.get("name") == "lf-request-duplicate"
           for label in issue.get("labels", [])):
        return "PEDIDO_POSIBLE_DUPLICADO"  # already marked; no second comment
    # Only a deliberate unlabeled event removing the duplicate marker can
    # override this decision. An ordinary opened/labeled event cannot.
    force = (event.get("action") == "unlabeled" and
             event.get("label", {}).get("name") == "lf-request-duplicate" and
             not any(row.get("name") == "lf-request-duplicate"
                     for row in issue.get("labels", [])))
    if not force:
        from pilot.request_duplicate import candidate, mark, DuplicateBlocked
        try:
            original = candidate(api, issue, request_text(issue.get("body")),
                                 root=Path(__file__).resolve().parents[2])
        except DuplicateBlocked as exc:
            raise Blocked(str(exc)) from exc
        if original is not None:
            mark(api, info["issue"], original)
            return "PEDIDO_POSIBLE_DUPLICADO"
    git("fetch", "--no-tags", "origin", "main")
    git("switch", "-c", branch, "origin/main")
    for path, raw in files.items():
        target = Path(path)
        if target.exists():
            raise Blocked("PEDIDO_YA_EXISTE")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    git("add", "--", *files.keys())
    git("-c", "user.name=github-actions[bot]",
        "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
        "commit", "-m", f"T9 issue #{info['issue']} request")
    from pilot.orchestrator.generated_branch_standards import synchronize
    synchronize(Path.cwd(), "request")
    git("push", "--set-upstream", "origin", branch)
    pr = api.call("POST", "/pulls", {
        "title": f"[T9] Pedido #{info['issue']} ({slug})",
        "head": branch, "base": "main", "draft": False,
        "body": f"Entrada automática desde #{info['issue']}. Solo contiene request.md y request_meta.json."})
    api.comment(info["issue"], f"Pedido registrado: {pr['html_url']}")
    return pr["html_url"]


def sweep(api: API) -> list[dict]:
    """R1: recover open issue requests whose intake event never ran.

    Reuses intake() authorization and duplicate checks. Independent issues are
    processed one at a time under lf-request-intake-global; no model calls.
    """
    candidates = []
    for page in range(1, 12):
        if page == 11:
            raise Blocked("R1_INTAKE_HISTORY_INCOMPLETE")
        rows = api.call("GET",
                        f"/issues?state=open&per_page=100&page={page}")
        if not isinstance(rows, list) or len(rows) > 100:
            raise Blocked("R1_INTAKE_HISTORY_INVALID")
        if any(not isinstance(item, dict) for item in rows):
            raise Blocked("R1_INTAKE_HISTORY_INVALID")
        candidates.extend(rows)
        if len(rows) < 100:
            break
    issues = {row.get("number"): row for row in candidates
              if not row.get("pull_request") and row.get("state") == "open"}
    if (len(issues) != len([x for x in candidates if not x.get("pull_request")
                            and x.get("state") == "open"])
            or any(type(number) is not int or number < 1 for number in issues)):
        raise Blocked("R1_INTAKE_HISTORY_INVALID")
    outcomes = []
    for number in sorted(issues):
        issue = issues[number]
        # The opened event can be lost before lf-request is applied. Only
        # issue-form-shaped entries are candidates; intake reattests author,
        # exact bytes, and duplicate policy before any mutation.
        if not (str(issue.get("body") or "").startswith(FIELD + "\n")
                and str(issue.get("title") or "").startswith("Pedido:")):
            continue
        try:
            # An intentional removal of the duplicate marker is an override
            # event. Rebuild it only from the actual latest GitHub label event.
            action = "opened"
            current_labels = {x.get("name") for x in issue.get("labels", [])
                              if isinstance(x, dict)}
            if "lf-request-duplicate" not in current_labels:
                events = api.call("GET", f"/issues/{number}/events?per_page=100")
                if (not isinstance(events, list) or len(events) >= 100
                        or any(not isinstance(x, dict) for x in events)):
                    raise Blocked("R1_INTAKE_EVENTS_INCOMPLETE")
                markers = [x for x in events if
                           (x.get("event") in ("labeled", "unlabeled")
                            and isinstance(x.get("label"), dict)
                            and x["label"].get("name") == "lf-request-duplicate")]
                if markers and markers[-1]["event"] == "unlabeled":
                    action = "unlabeled"
            event = {"action": action, "issue": issue}
            if action == "unlabeled":
                event["label"] = {"name": "lf-request-duplicate"}
            result = intake(api, event)
            if isinstance(result, str) and result.startswith("https://github.com/"):
                branch = f"lf/request/req-{number}"
                prs = api.call("GET",
                               f"/pulls?state=all&head=paulozterra:{branch}&per_page=100")
                if (not isinstance(prs, list) or len(prs) != 1 or
                        prs[0].get("head", {}).get("ref") != branch or
                        type(prs[0].get("number")) is not int or
                        not re.fullmatch(r"[0-9a-f]{40}",
                                         prs[0].get("head", {}).get("sha") or "")):
                    raise Blocked("R1_INTAKE_PR_UNRESOLVED")
                pr = prs[0]
                api.call("POST", "/actions/workflows/ci.yml/dispatches",
                         {"ref": branch, "inputs": {
                             "pr_number": str(pr["number"]),
                             "pr_sha": pr["head"]["sha"]}})
                outcomes.append({"issue": number, "status": "R1_INTAKE_PR_CREATED"})
            else:
                outcomes.append({"issue": number, "status": result})
        except (Blocked, OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
            raw = str(exc)
            code = raw if re.fullmatch(r"[A-Z][A-Z0-9_]{3,100}", raw) else (
                "R1_INTAKE_RECONCILE_FAILED")
            outcomes.append({"issue": number, "status": "BLOCKED", "code": code})
    return outcomes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", default=os.environ.get("GITHUB_EVENT_PATH"))
    parser.add_argument("--sweep", action="store_true")
    args = parser.parse_args()
    if os.environ.get("GITHUB_REPOSITORY") != REPO:
        raise Blocked("PEDIDO_REPOSITORIO_INVALIDO")
    if args.sweep:
        if os.environ.get("GITHUB_EVENT_NAME") != "schedule":
            raise Blocked("R1_INTAKE_SWEEP_EVENT_INVALID")
        print(json.dumps(sweep(API(os.environ.get("GH_TOKEN", ""))), sort_keys=True))
        return
    event = json.loads(Path(args.event).read_text(encoding="utf-8"))
    action = event.get("action")
    if action not in ("opened", "labeled", "unlabeled"):
        raise Blocked("PEDIDO_EVENTO_INVALIDO")
    if action in ("labeled", "unlabeled") and event.get("label", {}).get("name") != (
            "lf-request" if action == "labeled" else "lf-request-duplicate"):
        return
    print(intake(API(os.environ.get("GH_TOKEN", "")), event))


if __name__ == "__main__":
    try:
        main()
    except Blocked as error:
        print(str(error), flush=True)
        raise SystemExit(1)
