#!/usr/bin/env python3
"""Tiempo por paso de un pedido de la ruta, solo lectura sobre GitHub.

Reconstruye la línea de tiempo de un pedido (req-NNN) desde sus PRs y sus
issues de examen, y reparte el tiempo en: trabajo de la ruta (PR abierto →
integrado), espera entre pasos, y esperas con causa conocida (examinador,
GPT, retiros E2). No instrumenta nada: usa lo que GitHub ya guarda.

Uso: python3 pilot/metrics/request_timeline.py req-652 [--md salida.md]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime

REPO = "paulozterra/lf-programming-sandbox"

STAGES = (  # (prefijo de rama o patrón de título, paso)
    ("lf/request/", "T9 entrada"),
    ("lf/generated-t7/", "T7 análisis"),
    ("exam/", "Examen (PR)"),
    ("lf/exam-retire/", "Retiro E2"),
    ("lf/native-registration/", "Registro CP3.6"),
    ("lf/native-integration/", "Integración CP3.5"),
    ("lf/evidence/", "Evidencia"),
    ("lf/chain-complete/", "Cierre"),
)


def gh(path: str):
    out = subprocess.run(["gh", "api", path], check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def ts(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def dur(seconds: float) -> str:
    m = int(round(seconds / 60))
    return f"{m // 60}h{m % 60:02d}" if m >= 60 else f"{m} min"


def stage_of(head: str) -> str | None:
    return next((name for prefix, name in STAGES if head.startswith(prefix)), None)


def task_of(head: str, request: str) -> str:
    tail = head.split("/", 2)[-1]
    tail = re.sub(r"-(run-\d+|[0-9a-f]{12})$", "", tail)
    return "(pedido)" if tail.startswith(request) or tail.endswith("-" + request) else tail


def collect(request: str):
    slug = request.replace("-", "")
    pulls = []
    for page in range(1, 4):
        rows = gh(f"repos/{REPO}/pulls?state=all&sort=created&direction=desc&per_page=100&page={page}")
        pulls += [r for r in rows if re.search(rf"{request}\b|{slug}", r["head"]["ref"])]
        if len(rows) < 100:
            break
    events = []
    for p in pulls:
        stage = stage_of(p["head"]["ref"])
        if stage is None:
            continue
        end = p["merged_at"] or p["closed_at"]
        events.append({"task": task_of(p["head"]["ref"], request), "stage": stage,
                       "pr": p["number"], "start": ts(p["created_at"]), "end": ts(end),
                       "outcome": "integrado" if p["merged_at"] else ("cerrado" if end else "abierto")})
    issue = next((i for i in gh(f"repos/{REPO}/issues?state=all&per_page=100&labels=lf-request")
                  if i["title"].endswith(request.split("-")[1]) or str(i["number"]) == request.split("-")[1]), None)
    exams = [i for i in gh(f"repos/{REPO}/issues?state=all&labels=exam-request&per_page=100")
             if i["title"].startswith("EXAM_REQUEST: " + slug)]
    for i in exams:
        task = i["title"].split(": ", 1)[1]
        events.append({"task": task, "stage": "Pedido de examen", "pr": i["number"],
                       "start": ts(i["created_at"]), "end": None, "outcome": "issue"})
        for c in gh(f"repos/{REPO}/issues/{i['number']}/comments?per_page=100"):
            body = c["body"]
            kind = ("Examinador reserva" if "escribiendo el examen" in body else
                    "Examinador bloqueado" if "bloqueado" in body and "Examinador" in body else
                    "Examinador publica" if "examen publicado" in body else
                    "Aviso de retiro E2" if body.startswith("Examen retirado") else None)
            if kind:
                events.append({"task": task, "stage": kind, "pr": i["number"],
                               "start": ts(c["created_at"]), "end": None, "outcome": "comentario"})
    return issue, sorted(events, key=lambda e: e["start"])


def report(request: str) -> str:
    issue, events = collect(request)
    now = datetime.now(tz=events[0]["start"].tzinfo) if events else None
    origin = ts(issue["created_at"]) if issue else events[0]["start"]
    lines = [f"# Tiempos de {request}", "",
             f"Pedido abierto: {origin:%Y-%m-%d %H:%M} UTC · medido: {now:%Y-%m-%d %H:%M} UTC · "
             f"transcurrido: {dur((now - origin).total_seconds())}", ""]
    tasks = []
    for e in events:
        if e["task"] not in tasks:
            tasks.append(e["task"])
    totals: dict[str, float] = {}
    for task in tasks:
        rows = [e for e in events if e["task"] == task]
        lines += [f"## {task}", "", "| Paso | # | Inicio (UTC) | Duración | Espera previa | Resultado |",
                  "|---|---|---|---|---|---|"]
        previous = None
        for e in rows:
            span = ((e["end"] or now) - e["start"]).total_seconds() if e["outcome"] not in ("issue", "comentario") else None
            gap = (e["start"] - previous).total_seconds() if previous else None
            if span is not None:
                totals[e["stage"]] = totals.get(e["stage"], 0) + span
            lines.append(f"| {e['stage']} | {e['pr']} | {e['start']:%m-%d %H:%M} | "
                         f"{dur(span) + (' (en curso)' if e['end'] is None else '') if span is not None else '—'} | "
                         f"{dur(gap) if gap is not None else '—'} | {e['outcome']} |")
            previous = e["end"] or e["start"]
        lines.append("")
    lines += ["## Tiempo con PR abierto, por paso", "", "| Paso | Total |", "|---|---|"]
    lines += [f"| {k} | {dur(v)} |" for k, v in sorted(totals.items(), key=lambda kv: -kv[1])]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("request")
    parser.add_argument("--md")
    args = parser.parse_args()
    text = report(args.request)
    if args.md:
        open(args.md, "w", encoding="utf-8").write(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
