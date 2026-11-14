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


def intake(api: API, event: dict):
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
    git("push", "--set-upstream", "origin", branch)
    pr = api.call("POST", "/pulls", {
        "title": f"[T9] Pedido #{info['issue']} ({slug})",
        "head": branch, "base": "main", "draft": False,
        "body": f"Entrada automática desde #{info['issue']}. Solo contiene request.md y request_meta.json."})
    api.comment(info["issue"], f"Pedido registrado: {pr['html_url']}")
    return pr["html_url"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", default=os.environ.get("GITHUB_EVENT_PATH"))
    args = parser.parse_args()
    if os.environ.get("GITHUB_REPOSITORY") != REPO:
        raise Blocked("PEDIDO_REPOSITORIO_INVALIDO")
    event = json.loads(Path(args.event).read_text(encoding="utf-8"))
    action = event.get("action")
    if action not in ("opened", "labeled"):
        raise Blocked("PEDIDO_EVENTO_INVALIDO")
    if action == "labeled" and event.get("label", {}).get("name") != "lf-request":
        return
    print(intake(API(os.environ.get("GH_TOKEN", "")), event))


if __name__ == "__main__":
    try:
        main()
    except Blocked as error:
        print(str(error), flush=True)
        raise SystemExit(1)
