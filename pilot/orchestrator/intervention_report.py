#!/usr/bin/env python3
"""T0 — Intervention report for one request (pedido).

Deterministic, evidence-only. It reads git history (and optionally GitHub
label events) and classifies every change that belongs to a request:

  AUTOMATIC          produced by github-actions[bot] (route machinery)
  ALLOWED_HUMAN      the request text itself (pilot/runs/<p>/request.md)
  EXAMINER_EXPECTED  independent examiner material (encrypted exams, their
                     metadata, visible checks) committed by the examiner
  INTERVENTION       anything else committed by a person or a chat agent
                     (Paulo/GPT share the same GitHub identity; Claude has its own)

It never trusts what an agent declares: only who committed which path.
Output: JSON (stdout or --out) and Markdown (--markdown) with
``INTERVENCION_MANUAL: SI|NO``.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
BOT_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"
CLAUDE_EMAIL = "noreply@anthropic.com"

# Specific findings first; the first matching rule wins.
FINDINGS = [
    ("pilot/runs/{p}/planning_fixture.json", "MANUAL_LOT_DIVISION",
     "División en lotes / áreas / rutas escrita a mano (fixture simulado)"),
    ("pilot/runs/{p}/owner_area_decision.json", "MANUAL_AREA_DECISION",
     "Decisión manual de área (owner)"),
    ("pilot/runs/{p}/templates/*", "MANUAL_TASK_TEMPLATE",
     "Plantilla de tarea escrita a mano"),
    ("pilot/orchestrator/chain_plans/{p}.json", "MANUAL_CHAIN_PLAN",
     "Plan de cadena escrito a mano"),
    ("pilot/worker_v08/native_tasks/*", "MANUAL_REGISTRATION",
     "Registro de tarea ejecutado a mano (no por la ruta)"),
    (".lf/worker-context/*", "MANUAL_REGISTRATION",
     "Contexto de tarea registrado a mano"),
    ("pilot/runs/{p}/proposal_requests/*", "MANUAL_REGISTRATION",
     "Paquete de tarea exportado a mano"),
    ("pilot/runs/{p}/analysis.json", "MANUAL_COMMIT_OF_GENERATED",
     "Salida de Análisis/planificación comiteada a mano (no por la ruta)"),
    ("pilot/runs/{p}/state.json", "MANUAL_COMMIT_OF_GENERATED",
     "Estado del pedido comiteado a mano"),
    ("pilot/runs/{p}/lots.json", "MANUAL_COMMIT_OF_GENERATED",
     "Lotes comiteados a mano"),
    ("contracts/*.openapi.yaml", "MANUAL_CONTRACT", "Contrato OpenAPI escrito a mano"),
    ("*_SPEC.md", "MANUAL_CONTRACT", "Contrato/especificación escrita a mano"),
    ("*/src/test/*", "MANUAL_TEST_EDIT", "Test existente modificado a mano"),
    ("*pom.xml", "MANUAL_BASE_PREP", "Dependencias/build preparados a mano"),
    ("*package.json", "MANUAL_BASE_PREP", "Dependencias/build preparados a mano"),
    ("*application.properties", "MANUAL_BASE_PREP", "Configuración preparada a mano"),
    ("*.env.example", "MANUAL_BASE_PREP", "Configuración de ejemplo preparada a mano"),
    ("db/README.md", "MANUAL_BASE_PREP", "Estructura base preparada a mano"),
    ("*/src/main/*", "MANUAL_CODE", "Código de la aplicación escrito a mano"),
    ("frontend/src/*", "MANUAL_CODE", "Código de la aplicación escrito a mano"),
    ("db/migration/*", "MANUAL_CODE", "Migración escrita a mano"),
]
EXAMINER = ["pilot/holdouts/*", "pilot/runs/{p}/claude_meta/*", "*/visible-tests/*"]
IGNORED = ["standards/CAMBIOS.md", "standards/changes/*", "pilot/runs/*/INTERVENTION_REPORT.*",
           "pilot/runs/*/H_REPORT.md", "pilot/runs/*/evidence/*"]
# Route tooling built while running a request: reported apart, not counted
# as an intervention in the request itself (it is development of the route).
TOOLING = [".github/workflows/*", "pilot/orchestrator/*.py", "pilot/worker_v08/*.py",
           "pilot/*.py", "standards/tools/*"]


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], check=True,
                          capture_output=True, text=True).stdout


def actor(email: str, name: str) -> str:
    if email == BOT_EMAIL or name == "github-actions[bot]" or name == "sandbox-train[bot]":
        return "BOT"
    if email == CLAUDE_EMAIL:
        return "CLAUDE"
    return "PAULO_O_GPT"


def tasks_of(p: str, rev: str) -> list[str]:
    names = set()
    base = f"pilot/runs/{p}/"
    for path in git("ls-tree", "-r", "--name-only", rev, base).split():
        m = re.match(re.escape(base) + r"(?:claude_meta|templates|proposal_requests)/([a-z0-9_-]+)\.", path)
        if m:
            names.add(m.group(1))
    try:
        plan = json.loads(git("show", f"{rev}:pilot/orchestrator/chain_plans/{p}.json"))
        for lot in plan.get("lots", plan.get("tasks", [])):
            if isinstance(lot, dict) and isinstance(lot.get("task_name"), str):
                names.add(lot["task_name"])
    except subprocess.CalledProcessError:
        pass
    return sorted(n for n in names if SLUG.fullmatch(n))


def write_paths(p: str, tasks: list[str], rev: str) -> list[str]:
    out = set()
    try:
        for lot in json.loads(git("show", f"{rev}:pilot/runs/{p}/lots.json")).get("lots", []):
            out.update(x for x in lot.get("write_paths", []) if isinstance(x, str) and "*" not in x)
    except (subprocess.CalledProcessError, ValueError):
        pass
    for t in tasks:
        try:
            spec = json.loads(git("show", f"{rev}:pilot/worker_v08/native_tasks/{t}.json"))["task_spec"]
            out.update(x for x in spec.get("write_path_patterns", []) if isinstance(x, str) and "*" not in x)
        except (subprocess.CalledProcessError, ValueError, KeyError):
            pass
    return sorted(out)


def scope_paths(p: str, tasks: list[str], rev: str = "HEAD") -> list[str]:
    paths = [f"pilot/runs/{p}/", f"pilot/orchestrator/chain_plans/{p}.json"] + write_paths(p, tasks, rev)
    for t in tasks:
        paths += [f"pilot/worker_v08/native_tasks/{t}.json", f"pilot/holdouts/{t}.oracle.json.age",
                  f".lf/worker-context/{t}/"]
    return paths


def classify(path: str, who: str, p: str) -> tuple[str, str, str]:
    pat = lambda x: x.replace("{p}", p)
    if any(fnmatch.fnmatch(path, pat(x)) for x in IGNORED):
        return "IGNORED", "", ""
    if path == f"pilot/runs/{p}/request.md":
        return "ALLOWED_HUMAN", "REQUEST", "Texto del pedido"
    if any(fnmatch.fnmatch(path, pat(x)) for x in EXAMINER) and who in ("CLAUDE", "BOT"):
        return "EXAMINER_EXPECTED", "EXAMINER", "Material del examinador independiente"
    if who == "BOT":
        return "AUTOMATIC", "ROUTE", "Producido por la ruta"
    if any(fnmatch.fnmatch(path, x) for x in TOOLING):
        return "TOOLING", "ROUTE_TOOLING_CHANGE", "Cambio de herramientas de la ruta (no cuenta para el pedido)"
    for rule, code, desc in FINDINGS:
        if fnmatch.fnmatch(path, pat(rule)):
            return "INTERVENTION", code, desc
    return "INTERVENTION", "MANUAL_OTHER", "Otro cambio manual dentro del pedido"


def collect(p: str, rev: str) -> dict:
    tasks = tasks_of(p, rev)
    roots = scope_paths(p, tasks, rev)
    # Time-bound the request: only from the commit that introduced its request.md.
    first = git("log", rev, "--diff-filter=A", "--format=%H", "--", f"pilot/runs/{p}/request.md").split()
    if not first:
        raise SystemExit("REQUEST_NOT_FOUND")
    window = f"{first[-1]}^..{rev}"
    log = git("log", window, "--no-merges", "--format=%x1e%H%x1f%an%x1f%ae%x1f%s", "--name-only",
              "--", *roots)
    commits = []
    for chunk in log.split("\x1e"):
        if not chunk.strip():
            continue
        head, _, files = chunk.partition("\n")
        sha, name, email, subject = head.split("\x1f", 3)
        commits.append((sha, name, email, subject))
    rows = []
    for sha, name, email, subject in commits:
        who = actor(email, name)
        # every file of an in-scope commit counts (base prep, tests, contracts...)
        for path in git("show", "--no-renames", "--name-only", "--format=", sha).split():
            verdict, code, desc = classify(path, who, p)
            if verdict == "IGNORED":
                continue
            rows.append({"commit": sha[:12], "actor": who, "subject": subject[:120], "path": path,
                         "verdict": verdict, "code": code, "description": desc})
    return {"tasks": tasks, "scope_roots": roots, "rows": rows,
            "commits": [c[0] for c in commits]}


def label_events(prs: list[int]) -> list[dict]:
    token, repo = os.environ.get("GH_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        return []
    out = []
    for n in prs:
        req = urllib.request.Request(f"https://api.github.com/repos/{repo}/issues/{n}/events?per_page=100",
                                     headers={"Authorization": "Bearer " + token,
                                              "Accept": "application/vnd.github+json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                events = json.load(r)
        except Exception:  # evidence is optional; absence is reported, never invented
            out.append({"pr": n, "verdict": "UNKNOWN", "code": "LABEL_EVENTS_UNAVAILABLE"})
            continue
        for e in events:
            if e.get("event") == "labeled" and e.get("label", {}).get("name") == "ready-to-merge":
                login = (e.get("actor") or {}).get("login", "")
                bot = login.endswith("[bot]")
                out.append({"pr": n, "actor": login, "verdict": "AUTOMATIC" if bot else "INTERVENTION",
                            "code": "" if bot else "MANUAL_LABEL",
                            "description": "Etiqueta de fusión puesta por la ruta" if bot
                            else "Etiqueta ready-to-merge puesta a mano"})
    return out


def prs_in_scope(commits: list[str]) -> list[int]:
    """PRs that carried the in-scope commits (GitHub API; optional)."""
    token, repo = os.environ.get("GH_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        return []
    nums = set()
    for sha in commits:
        req = urllib.request.Request(f"https://api.github.com/repos/{repo}/commits/{sha}/pulls",
                                     headers={"Authorization": "Bearer " + token,
                                              "Accept": "application/vnd.github+json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                nums.update(x["number"] for x in json.load(r) if x.get("merged_at"))
        except Exception:
            continue
    return sorted(nums)


def report(p: str, rev: str = "HEAD", with_labels: bool = True) -> dict:
    if not SLUG.fullmatch(p):
        raise SystemExit("REQUEST_ID_INVALID")
    data = collect(p, rev)
    labels = label_events(prs_in_scope(data["commits"])) if with_labels else []
    interventions = [r for r in data["rows"] if r["verdict"] == "INTERVENTION"]
    interventions += [x for x in labels if x.get("verdict") == "INTERVENTION"]
    summary: dict[str, list[str]] = {}
    for r in interventions:
        summary.setdefault(r["code"], [])
        key = r.get("path") or f"PR #{r.get('pr')}"
        if key not in summary[r["code"]]:
            summary[r["code"]].append(key)
    return {
        "schema_version": "LF_INTERVENTION_REPORT_V1",
        "request_id": p,
        "revision": git("rev-parse", rev).strip(),
        "tasks": data["tasks"],
        "intervencion_manual": "SI" if interventions else "NO",
        "intervention_count": len(interventions),
        "by_code": {k: sorted(v) for k, v in sorted(summary.items())},
        "label_events": labels,
        "rows": data["rows"],
        "notes": ["PAULO_O_GPT: Paulo y GPT comparten identidad de GitHub; no se distinguen.",
                  "ALLOWED_HUMAN y EXAMINER_EXPECTED no cuentan como intervención."],
    }


def markdown(r: dict) -> str:
    lines = [f"# Informe de intervenciones — `{r['request_id']}`", "",
             f"**INTERVENCION_MANUAL: {r['intervencion_manual']}** ({r['intervention_count']} hallazgos) "
             f"· revisión `{r['revision'][:12]}` · tareas: {', '.join(r['tasks']) or '—'}", ""]
    if r["by_code"]:
        lines += ["| Código | Rutas / PR |", "|---|---|"]
        for code, paths in r["by_code"].items():
            lines.append(f"| `{code}` | {'<br>'.join('`'+x+'`' for x in paths)} |")
        lines.append("")
    auto = sum(1 for x in r["rows"] if x["verdict"] == "AUTOMATIC")
    tool = sorted({x["path"] for x in r["rows"] if x["verdict"] == "TOOLING"})
    exam = sum(1 for x in r["rows"] if x["verdict"] == "EXAMINER_EXPECTED")
    lines += [f"Automático: {auto} · Examinador (previsto): {exam} · Pedido (previsto): "
              f"{sum(1 for x in r['rows'] if x['verdict'] == 'ALLOWED_HUMAN')}", ""]
    if tool:
        lines += ["Cambios de herramientas de la ruta hechos durante el pedido (no cuentan): "
                  + ", ".join("`" + x + "`" for x in tool), ""]
    lines += ["> " + n for n in r["notes"]]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--request", required=True)
    ap.add_argument("--rev", default="HEAD")
    ap.add_argument("--no-labels", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--markdown")
    a = ap.parse_args()
    r = report(a.request, a.rev, not a.no_labels)
    raw = json.dumps(r, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if a.out:
        Path(a.out).write_text(raw, encoding="utf-8")
    if a.markdown:
        Path(a.markdown).write_text(markdown(r), encoding="utf-8")
    print(json.dumps({"request_id": r["request_id"], "intervencion_manual": r["intervencion_manual"],
                      "by_code": {k: len(v) for k, v in r["by_code"].items()}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
