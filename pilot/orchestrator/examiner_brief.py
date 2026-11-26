#!/usr/bin/env python3
"""T58: brief for the automatic independent examiner.

Gathers mechanically, from public route artifacts only, everything the
examiner needs to write one hidden exam, so the model does not explore the
repository: the lot template (objective, base, write and context paths,
visible acceptance commands), the text of every fiche rule the lot carries,
the public contract skeleton, the current content of existing write paths
(MODIFY) and the exact publish command. Writes ``brief.json`` and ``brief.md``
into a scratch directory OUTSIDE the repository.
"""
from __future__ import annotations
# Resolve the trusted repository package for direct script execution.
import sys as _project_sys
from pathlib import Path as _project_Path
_project_sys.path.insert(0, str(_project_Path(__file__).resolve().parents[2]))
from pilot.config.project_config import storage_path

import argparse
import json
import re
from pathlib import Path

ROOT = _project_Path(__file__).resolve().parents[2]
TASK = re.compile(r"[a-z][a-z0-9_-]{0,31}")
SLUG = re.compile(r"req-[1-9][0-9]*")
MAX_FILE_BYTES = 60_000


class BriefBlocked(ValueError):
    pass


def _json(path: Path):
    if path.is_symlink() or not path.is_file():
        raise BriefBlocked("EXAMINER_BRIEF_MISSING:" + path.name)
    return json.loads(path.read_text("utf-8"))


def lot_for(lots: dict, write_paths: list[str]) -> dict:
    rows = [lot for lot in lots.get("lots", []) if isinstance(lot, dict)
            and sorted(lot.get("write_paths") or []) == sorted(write_paths)]
    if len(rows) != 1:
        raise BriefBlocked("EXAMINER_BRIEF_LOT_UNRESOLVED")
    return rows[0]


def source_fiche_rules(root: Path, requirement_ids: list[str]) -> dict:
    """Resolve second-screen requirement IDs through their explicit source links.

    The canonical trace is the lot REQ suffix, not a normalized guess at the
    original rule code. Only a unique rule in the same source, with matching
    evidence and effective-rule link, can authorize that alias.
    """
    wanted = {r for r in requirement_ids if isinstance(r, str) and r.startswith("REQ-")}
    candidates: dict[str, list] = {}
    for path in sorted((root / "analysis" / "fixtures").glob("*/source.json")):
        if path.is_symlink():
            continue
        try:
            data = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict) or data.get("schema_version") != "SECOND_SCREEN_SOURCE_V1":
            continue
        screen = data.get("screen_contract")
        effective = data.get("effective_rules")
        requirements = data.get("requirements")
        if not isinstance(requirements, list):
            continue
        for req in requirements:
            if not isinstance(req, dict):
                continue
            requirement_id = req.get("requirement_id")
            if not isinstance(requirement_id, str) or requirement_id not in wanted:
                continue
            canonical = requirement_id[len("REQ-"):]
            rows = candidates.setdefault(canonical, [])
            source_code = req.get("source_requirement_id")
            if not isinstance(source_code, str) or not isinstance(screen, dict) or not isinstance(effective, dict):
                rows.append(None)
                continue
            rules = screen.get("rules")
            refs = req.get("evidence_refs")
            matches = [r for r in rules if isinstance(r, dict) and r.get("code") == source_code] if isinstance(rules, list) else []
            link = effective.get(source_code)
            if len(matches) != 1 or not isinstance(link, dict) or not isinstance(refs, list):
                rows.append(None)
                continue
            rule = matches[0]
            ref = rule.get("source_ref")
            if (not isinstance(ref, str) or not ref or ref not in refs
                    or link.get("code") != source_code or link.get("source_ref") != ref):
                rows.append(None)
                continue
            rows.append({**link, **rule, "fixture": path.parent.name,
                         "code": canonical, "source_rule_code": source_code})
    return {code: rows[0] for code, rows in candidates.items()
            if len(rows) == 1 and rows[0] is not None}


def fiche_rules(root: Path, requirement_ids: list[str]) -> dict:
    """Fiche text keyed by the canonical trace code of each lot requirement."""
    wanted = {r[len("REQ-"):] for r in requirement_ids if r.startswith("REQ-")}
    found = source_fiche_rules(root, requirement_ids)
    for path in sorted((root / "analysis" / "fixtures").glob("*/effective_rules.json")):
        try:
            data = json.loads(path.read_text("utf-8"))
        except ValueError:
            continue
        for rule in data.get("rules", []) if isinstance(data, dict) else []:
            code = rule.get("code") if isinstance(rule, dict) else None
            if code in wanted and code not in found:
                found[code] = {"fixture": path.parent.name, **rule}
    return found


def _read_small(root: Path, rel: str) -> str | None:
    path = root / rel
    if path.is_symlink() or not path.is_file():
        return None
    data = path.read_bytes()[:MAX_FILE_BYTES]
    return data.decode("utf-8", "replace")


def build_brief(root: Path, request: str, task: str, write_paths: list[str],
                requirement_ids: list[str], issue: int | None = None) -> dict:
    if not TASK.fullmatch(task) or not SLUG.fullmatch(request):
        raise BriefBlocked("EXAMINER_BRIEF_IDENTITY_INVALID")
    folder = storage_path("requests_root", root=root) / request
    template = _json(folder / "templates" / f"{task}.task.json")
    spec = template.get("task_spec")
    if not isinstance(spec, dict):
        raise BriefBlocked("EXAMINER_BRIEF_TEMPLATE_INVALID")
    if sorted(spec.get("write_path_patterns") or []) != sorted(write_paths):
        raise BriefBlocked("EXAMINER_BRIEF_SCOPE_MISMATCH")
    lot = lot_for(_json(folder / "lots.json"), write_paths)
    rules = fiche_rules(root, requirement_ids)
    missing = sorted({r[len("REQ-"):] for r in requirement_ids} - set(rules))
    context = {}
    for rel in spec.get("context_path_patterns") or []:
        if isinstance(rel, str) and "*" not in rel:
            text = _read_small(root, rel)
            if text is not None:
                context[rel] = text
    existing = {rel: _read_small(root, rel) for rel in write_paths
                if _read_small(root, rel) is not None}
    return {
        "schema_version": "LF_EXAMINER_BRIEF_V1",
        "issue": issue, "request": request, "task": task,
        "area": lot.get("area"), "lot": lot.get("id"),
        "lot_kind": lot.get("lot_kind"),
        # A characterization lot pins existing behavior: the examiner needs
        # the current files it describes, not new code to implement.
        "characterized_file_content": ({rel: _read_small(root, rel)
                                        for rel in lot.get("characterized_files") or []
                                        if _read_small(root, rel) is not None}
                                       if lot.get("lot_kind") == "CHARACTERIZATION" else {}),
        "depends_on": lot.get("depends_on") or [],
        # The template carries a placeholder until registration: the exam is
        # written against current main, which is the lot's base when T4 opens
        # the request (all dependencies already integrated).
        "base_head_sha": (spec.get("base_head_sha")
                          if re.fullmatch(r"[0-9a-f]{40}", str(spec.get("base_head_sha")))
                          else "main actual"),
        "objective": spec.get("objective"),
        "write_paths": write_paths,
        "protected_path_patterns": spec.get("protected_path_patterns") or [],
        "visible_acceptance_commands": spec.get("acceptance_commands") or [],
        "requirement_ids": requirement_ids,
        "rules": rules,
        "rules_without_text": missing,
        "context_files": context,
        "existing_write_path_content": existing,
        "publish": {
            "command": ["python3", "pilot/orchestrator/publish_exam.py",
                        "--task", task, "--request", request,
                        "--script", "<scratch>/exam.py", "--trace", "<scratch>/trace.json",
                        "--family", "<area-lowercase>", "--version", "v1",
                        "--worktree", "<scratch>/main", "--reference", "<scratch>/ref",
                        "--mutants", "<scratch>/mut", "--derived-from", "<ficha y reglas>"],
            "trace_kinds": ["rule:<CODE canónico mostrado en rules del lote>", "contract:<ruta>",
                            f"request:{request} <decisión>", "env:<build/arranque>"],
            "branch": f"exam/{task}",
            "paths": [f"pilot/holdouts/{task}.oracle.json.age",
                      f"pilot/holdouts/{task}.reference.json.age",
                      f"pilot/runs/{request}/claude_meta/{task}.json"],
        },
    }


def render_md(brief: dict) -> str:
    lines = [f"# Brief del examinador: {brief['task']} ({brief['area']}, {brief['request']})", "",
             f"- Lote: `{brief['lot']}` · base `{brief['base_head_sha']}` · issue #{brief['issue']}",
             f"- Depende de: {', '.join(brief['depends_on']) or '—'}",
             "- Rutas de escritura: " + ", ".join(f"`{p}`" for p in brief["write_paths"]),
             "", "## Objetivo del lote", "", str(brief.get("objective") or "—"), "",
             "## Reglas de la ficha (lo único que el examen puede exigir)", ""]
    for code, rule in sorted(brief["rules"].items()):
        lines.append(f"### {code} — {rule.get('title', '')}")
        lines.append("```json")
        lines.append(json.dumps({k: v for k, v in rule.items() if k not in ("source_ref",)},
                                ensure_ascii=False, indent=1))
        lines.append("```")
    if brief["rules_without_text"]:
        lines += ["", "Sin texto en la ficha (no exigir): "
                  + ", ".join(brief["rules_without_text"])]
    lines += ["", "## Pruebas visibles del lote", "```json",
              json.dumps(brief["visible_acceptance_commands"], ensure_ascii=False, indent=1),
              "```", "", "## Archivos de contexto"]
    for rel in brief["context_files"]:
        lines.append(f"- `{rel}` (en brief.json)")
    if brief["existing_write_path_content"]:
        lines += ["", "## Contenido actual de las rutas de escritura (MODIFY)"]
        for rel in brief["existing_write_path_content"]:
            lines.append(f"- `{rel}` (en brief.json)")
    lines += ["", "## Publicación", "```", " ".join(brief["publish"]["command"]), "```",
              "Rama `" + brief["publish"]["branch"] + "`; archivos: "
              + ", ".join(f"`{p}`" for p in brief["publish"]["paths"]), ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--write-paths", required=True, help="JSON list")
    parser.add_argument("--requirement-ids", required=True, help="JSON list")
    parser.add_argument("--issue", type=int, default=None)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        out = args.out.resolve()
        if out == args.root.resolve() or args.root.resolve() in out.parents:
            raise BriefBlocked("EXAMINER_BRIEF_OUT_INSIDE_REPO")
        brief = build_brief(args.root, args.request, args.task,
                            json.loads(args.write_paths), json.loads(args.requirement_ids),
                            args.issue)
        out.mkdir(parents=True, exist_ok=True)
        (out / "brief.json").write_text(json.dumps(brief, ensure_ascii=False, indent=1), "utf-8")
        (out / "brief.md").write_text(render_md(brief), "utf-8")
    except (BriefBlocked, ValueError) as exc:
        print(json.dumps({"status": "EXAMINER_BRIEF_BLOCKED", "detail": str(exc)[:200]}))
        return 2
    print(json.dumps({"status": "EXAMINER_BRIEF_READY", "out": str(out),
                      "rules": len(brief["rules"]),
                      "rules_without_text": brief["rules_without_text"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
