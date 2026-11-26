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
import hashlib
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


def _object(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError("SOURCE_FILE_MISSING")
    obj = json.loads(path.read_text("utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("SOURCE_OBJECT_INVALID")
    return obj


def _result(status: str, rule: dict | None = None) -> dict:
    return {"status": status, "rule": rule}


def _source_for_request(root: Path, request: str) -> tuple[str, Path | None, dict]:
    """Use the persisted A9 target and fixture provenance, never a global rule match."""
    if not SLUG.fullmatch(request):
        return "INVALID", None, {}
    try:
        analysis = _object(storage_path("requests_root", root=root) / request / "analysis.json")
        target = analysis["request_context"]["target_ref"]
        snapshot = analysis["programming_context_snapshot"]
        provenance = snapshot["source_snapshot_inputs"]["rule_fixture_provenance"]
        if not isinstance(target, str) or not target or snapshot["target"] != target:
            return "INVALID", None, {}
        ref = provenance["effective_rules.json"]
        match = re.fullmatch(r"fixture://([a-zA-Z0-9_-]+)/effective_rules\.json@[a-f0-9]{64}", ref)
        if not match:
            return "INVALID", None, {}
        folder = root / "analysis" / "fixtures" / match.group(1)
        if folder.is_symlink():
            return "INVALID", None, {}
        pin = _object(folder / "SOURCE_PIN.json")
        if pin.get("fixture_id") != target:
            return "INVALID", None, {}
        for other in sorted(folder.parent.glob("*/SOURCE_PIN.json")):
            if other.parent == folder:
                continue
            try:
                if _object(other).get("fixture_id") == target:
                    return "AMBIGUOUS", None, {}
            except (OSError, ValueError):
                continue
        return "VALID", folder, {"analysis": analysis, "pin": pin}
    except (OSError, ValueError, KeyError, TypeError):
        return "INVALID", None, {}


def _pinned_file(folder: Path, filename: str, digest: str) -> dict:
    path = folder / filename
    if path.is_symlink() or not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError("SOURCE_PIN_INVALID")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("SOURCE_PIN_MISMATCH")
    return _object(path)


def _rule_rows(data, key: str, value: str) -> list:
    if not isinstance(data, list):
        raise ValueError("SOURCE_ROWS_INVALID")
    return [r for r in data if isinstance(r, dict) and r.get(key) == value]


def resolve_fiche_rule(root: Path, request: str, code: str) -> dict:
    """Four-state resolution shared by brief and publication.

    Only the pinned source format determines the branch. An invalid or
    ambiguous association can never be rescued by a legacy file or text hit.
    """
    if code.startswith("STD-"):
        try:
            rows = _rule_rows(_object(root / "standards/catalog.json").get("rules"), "id", code)
            return _result("VALID", {**rows[0], "code": code}) if len(rows) == 1 else _result(
                "AMBIGUOUS" if rows else "MISSING")
        except (OSError, ValueError):
            return _result("INVALID")
    state, folder, binding = _source_for_request(root, request)
    if state != "VALID":
        return _result(state)
    pin, analysis = binding["pin"], binding["analysis"]
    req_id = "REQ-" + code
    try:
        planned = _rule_rows(analysis.get("requirements"), "requirement_id", req_id)
        if len(planned) != 1:
            return _result("AMBIGUOUS" if planned else "MISSING")
        if pin.get("schema_version") == "SOURCE_SCREEN_PIN_V1":
            if pin.get("source_file") != "source.json":
                return _result("INVALID")
            data = _pinned_file(folder, "source.json", pin.get("sha256"))
            if (data.get("schema_version") != "SECOND_SCREEN_SOURCE_V1"
                    or data.get("target_ref") != pin["fixture_id"]):
                return _result("INVALID")
            rows = _rule_rows(data.get("requirements"), "requirement_id", req_id)
            if len(rows) != 1:
                return _result("AMBIGUOUS" if rows else "MISSING")
            req = rows[0]
            source_code = req.get("source_requirement_id")
            if not isinstance(source_code, str) or not source_code:
                return _result("INVALID")
            screen = data.get("screen_contract")
            effective = data.get("effective_rules")
            if not isinstance(screen, dict) or not isinstance(effective, dict):
                return _result("INVALID")
            matches = _rule_rows(screen.get("rules"), "code", source_code)
            if len(matches) != 1:
                return _result("AMBIGUOUS" if matches else "INVALID")
            rule, link = matches[0], effective.get(source_code)
            ref, refs = rule.get("source_ref"), req.get("evidence_refs")
            if (not isinstance(ref, str) or not ref or not isinstance(refs, list)
                    or ref not in refs or not isinstance(link, dict)
                    or link.get("code") != source_code or link.get("source_ref") != ref):
                return _result("INVALID")
            # A9's simulation projects fixture rule references to lf_ops IDs.
            match = re.fullmatch(r"fixture://" + re.escape(folder.name) + r"/rules/([0-9]+)", ref)
            if ref.startswith("fixture://") and not match:
                return _result("INVALID")
            projected = "supabase://lf_ops.reglas/" + match.group(1) if match else ref
            planned_refs = planned[0].get("evidence_refs")
            if (not isinstance(planned_refs, list) or not ({ref, projected} & set(
                    r for r in planned_refs if isinstance(r, str)))
                    or planned[0].get("source_requirement_id") not in (source_code, code)):
                return _result("INVALID")
            return _result("VALID", {**link, **rule, "fixture": folder.name,
                                     "code": code, "source_rule_code": source_code})
        if pin.get("schema_version") != "SBX_FIXTURE_PIN_V1":
            return _result("INVALID")
        pins = _rule_rows(pin.get("files"), "file", "effective_rules.json")
        if len(pins) != 1:
            return _result("AMBIGUOUS" if pins else "INVALID")
        data = _pinned_file(folder, "effective_rules.json", pins[0].get("sha256"))
        rows = _rule_rows(data.get("rules"), "code", code)
        if len(rows) != 1:
            return _result("AMBIGUOUS" if rows else "MISSING")
        rule = rows[0]
        refs = planned[0].get("evidence_refs")
        if (not isinstance(rule.get("source_ref"), str) or not isinstance(refs, list)
                or rule["source_ref"] not in refs or planned[0].get("source_requirement_id") != code):
            return _result("INVALID")
        return _result("VALID", {**rule, "fixture": folder.name})
    except (OSError, ValueError, KeyError, TypeError):
        return _result("INVALID")


def fiche_rules(root: Path, request: str, requirement_ids: list[str]) -> tuple[dict, dict]:
    states = {r[len("REQ-"):]: resolve_fiche_rule(root, request, r[len("REQ-"):])
              for r in requirement_ids if isinstance(r, str) and r.startswith("REQ-")}
    found = {code: result["rule"] for code, result in states.items() if result["status"] == "VALID"}
    return found, {code: result["status"] for code, result in states.items()}

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
    bound = (lot.get("characterized_requirement_ids") if lot.get("lot_kind") == "CHARACTERIZATION"
             else lot.get("requirement_ids"))
    if (not isinstance(bound, list) or not all(isinstance(r, str) for r in bound)
            or not all(isinstance(r, str) for r in requirement_ids)
            or sorted(bound) != sorted(requirement_ids)):
        raise BriefBlocked("EXAMINER_BRIEF_REQUIREMENTS_MISMATCH")
    rules, rule_resolution = fiche_rules(root, request, requirement_ids)
    missing = sorted(code for code, state in rule_resolution.items() if state != "VALID")
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
        "rule_resolution": rule_resolution,
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
                  + ", ".join(f"{code} ({brief['rule_resolution'][code]})"
                              for code in brief["rules_without_text"])]
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
