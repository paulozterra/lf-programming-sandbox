#!/usr/bin/env python3
"""T56: the route consults the EKB before implementing and registers new errors.

Owner decision (Paulo, 20/11/2026, option B): the same EKB table, with the
route's own rows marked by ``source_context``; reading *content* is an
explicit exception to CLAUDE.md rule 3 (see CHG-0242).

Boundaries kept by this module:
- Reads and writes go only through the EKB's *existing* functions named in
  ``pilot/ekb/route_ekb.json``: the engineering lookup and the governed
  pipeline writer (which validates the catalogue, counts recurrences and
  emits an auditable event). The route never sends free SQL nor names a table.
- Only a fixed set of content columns is returned (never ``evidencia``) and
  every text is sanitised: URLs, e-mails, tokens, keys and Supabase refs are
  replaced by ``[REDACTADO]``. A row that would still look sensitive is
  dropped, never published.
- Content is written to the ``--out`` file only. stdout and errors carry
  counts, codes and code-class reasons; never server text or the URL.
- Writing needs a separate secret and is only allowed from a trusted step;
  the payload is validated and its text must already be clean (no
  redaction on write: a dirty entry is refused, not silently altered).
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

CONFIG = Path(__file__).resolve().parent / "route_ekb.json"
CATALOG = Path(__file__).resolve().parent / "route_error_catalog.json"
ROUTE_CODE = re.compile(r"[A-Z][A-Z0-9_]{2,60}")
CATALOG = Path(__file__).resolve().parent / "route_error_catalog.json"
ROUTE_CODE = re.compile(r"[A-Z][A-Z0-9_]{2,60}")
IDENT = re.compile(r"[a-z_][a-z0-9_]{0,62}(\.[a-z_][a-z0-9_]{0,62})?")
SECRET_NAME = re.compile(r"[A-Z][A-Z0-9_]{2,63}")
CODE = re.compile(r"LF-ROUTE-[A-Z0-9][A-Z0-9-]{2,78}")
TERM = re.compile(r"[\w .:/#+-]{2,60}")
CONTENT_FIELDS = ("codigo", "categoria", "titulo", "patron", "causa_raiz",
                  "prevencion", "validacion", "severidad", "frecuencia", "source_context")
WRITE_TEXT = ("titulo", "descripcion", "patron", "causa_raiz", "prevencion", "validacion")
# Catalogues enforced by the governed writer (kept identical here to fail early).
SEVERITIES = ("Low", "Medium", "High", "Critical")
ROOT_CAUSES = ("R1_NO_SABE", "R2_NO_VE", "R3_NO_PRIORIZA", "R4_NO_CUESTIONA",
               "R5_EROSION_PROCESO", "UNCLASSIFIED_WITH_REASON")
DETECTABILITY = ("LOUD_EARLY", "LOUD_LATE", "SILENT", "PROCESS_DEPENDENT")
ROLES = ("Builder", "Judge", "Auditor", "DevOps", "Architect")
PHASES = ("construction", "CI_VALIDATION", "E2E_EXECUTION", "EXECUTION", "governance")
SEV_RANK = {"critical": 0, "critica": 0, "alta": 1, "high": 1, "media": 2, "medium": 2}
EVIDENCE_REF = re.compile(r"(PR #\d{1,7}|run \d{6,14}|CHG-\d{4}|lote [\w.-]{1,60})(; (PR #\d{1,7}|run \d{6,14}|CHG-\d{4}|lote [\w.-]{1,60})){0,5}")
EXECUTION_ID = re.compile(r"gha-\d{6,14}-\d{1,3}")
MAX_TEXT = 2000
REDACTED = "[REDACTADO]"
SENSITIVE = [
    re.compile(r"\b[a-z][a-z0-9+.-]*://\S+", re.I),                      # any URL / DSN
    re.compile(r"\b[\w.+-]+@[\w-]+(\.[\w-]+)+\b"),                       # e-mail
    re.compile(r"\beyJ[\w-]{10,}\.[\w-]{10,}\.[\w-]{5,}"),               # JWT
    re.compile(r"\b(sk|pk|ghp|gho|ghs|github_pat|sbp|xox[abp])_[\w-]{10,}", re.I),  # API keys
    re.compile(r"\b[a-z]{20}\.supabase\.(co|in)\b", re.I),               # project host
    re.compile(r"\b(project_ref|password|passwd|secret|token|apikey|api_key)\s*[:=]\s*\S+", re.I),
    re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}"),                           # long opaque blobs
]


class EkbError(ValueError):
    pass


def load_config(path: Path = CONFIG) -> dict:
    try:
        cfg = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        raise EkbError("ROUTE_EKB_CONFIG_INVALID") from None
    ok = (cfg.get("schema_version") == "LF_ROUTE_EKB_V1"
          and isinstance(cfg.get("read_secret"), str) and SECRET_NAME.fullmatch(cfg["read_secret"])
          and isinstance(cfg.get("write_secret"), str) and SECRET_NAME.fullmatch(cfg["write_secret"])
          and cfg["read_secret"] != cfg["write_secret"]
          and all(isinstance(cfg.get(k), str) and IDENT.fullmatch(cfg[k])
                  for k in ("lookup_function", "writer_function"))
          and isinstance(cfg.get("operation_code"), str) and re.fullmatch(r"[A-Z][A-Z0-9_]{2,62}", cfg["operation_code"])
          and isinstance(cfg.get("source_ref"), str) and re.fullmatch(r"[\w.-]{3,80}", cfg["source_ref"])
          and isinstance(cfg.get("source_context"), str) and re.fullmatch(r"LF_ROUTE[A-Z_]*", cfg["source_context"])
          and isinstance(cfg.get("max_results"), int) and 1 <= cfg["max_results"] <= 50
          and cfg.get("store_evidence") is False)
    if not ok:
        raise EkbError("ROUTE_EKB_CONFIG_INVALID")
    return cfg


def sanitize(text: object) -> tuple[str, int]:
    if text is None:
        return "", 0
    value = str(text)[:MAX_TEXT]
    hits = 0
    for pattern in SENSITIVE:
        value, n = pattern.subn(REDACTED, value)
        hits += n
    return value, hits


def is_clean(text: str) -> bool:
    return all(not p.search(text) for p in SENSITIVE)


def _url(env: dict, secret: str) -> str:
    url = env.get(secret, "").strip().strip("'\"").strip()
    if not url:
        raise EkbError("ROUTE_EKB_UNAVAILABLE:SECRET_MISSING")
    if not url.startswith(("postgresql://", "postgres://")):
        raise EkbError("ROUTE_EKB_UNAVAILABLE:SECRET_MALFORMED")
    base, _, query = url.partition("?")
    kept = [kv for kv in query.split("&") if kv and kv.split("=")[0]
            not in ("pgbouncer", "connection_limit", "pool_timeout", "schema")]
    return base + ("?" + "&".join(kept) if kept else "")


def _psql(url: str, script: str, variables: dict[str, str], psql: str, env: dict) -> str:
    child = {k: v for k, v in env.items() if k in ("PATH", "HOME", "LANG", "LC_ALL")}
    child["PGCONNECT_TIMEOUT"] = "15"
    args = [psql, url, "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1"]
    for name, value in variables.items():
        args += ["-v", f"{name}={value}"]
    try:
        # Script via stdin: psql only interpolates :'var' outside -c.
        out = subprocess.run(args, input=script, capture_output=True, text=True,
                             timeout=60, env=child)
    except (OSError, subprocess.TimeoutExpired):
        raise EkbError("ROUTE_EKB_UNAVAILABLE:CLIENT") from None
    if out.returncode != 0:
        err = out.stderr.lower()
        kind = ("AUTH" if "password" in err or "authentication" in err else
                "PERMISSION" if "permission denied" in err else
                "SCHEMA" if "does not exist" in err else
                "NETWORK" if "could not" in err or "timeout" in err or "refused" in err
                or "connection to server" in err else "QUERY")
        state = re.search(r"error:\s+([0-9a-z]{5}):", err)
        raise EkbError("ROUTE_EKB_UNAVAILABLE:" + kind + (":" + state.group(1).upper() if state else ""))
    return out.stdout


def lookup(terms: list[str], *, area: str | None = None, cfg: dict | None = None,
           env: dict | None = None, psql: str = "psql") -> dict:
    cfg = cfg or load_config()
    clean_terms = sorted({t.strip() for t in terms if isinstance(t, str) and TERM.fullmatch(t.strip())})
    if area:
        if not re.fullmatch(r"[A-Z_]{2,20}", area):
            raise EkbError("ROUTE_EKB_AREA_INVALID")
        clean_terms = sorted(set(clean_terms) | {area})
    if not clean_terms:
        raise EkbError("ROUTE_EKB_TERMS_EMPTY")
    env = dict(os.environ if env is None else env)
    # The engineering lookup takes one phrase: ask once per term, in one
    # read-only transaction, and merge by code (ranked by terms matched).
    script = ("begin transaction read only;\n"
              f"select {cfg['lookup_function']}(t, null, :lim)::text "
              "from jsonb_array_elements_text(:'terms'::jsonb) t;\n"
              "rollback;\n")
    raw = _psql(_url(env, cfg["read_secret"]), script,
                {"terms": json.dumps(clean_terms), "lim": str(cfg["max_results"])}, psql, env)
    merged: dict[str, dict] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            doc = json.loads(line)
        except ValueError:
            raise EkbError("ROUTE_EKB_UNAVAILABLE:SHAPE") from None
        rows = doc.get("rows") if isinstance(doc, dict) else None
        if not isinstance(rows, list):
            raise EkbError("ROUTE_EKB_UNAVAILABLE:SHAPE")
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("codigo"), str):
                raise EkbError("ROUTE_EKB_UNAVAILABLE:SHAPE")
            if str(row.get("estado") or "").lower().startswith(("superseded", "candidate_rejected")):
                continue
            hit = merged.setdefault(row["codigo"], {"row": row, "hits": 0})
            hit["hits"] += 1
    ranked = sorted(merged.values(), key=lambda h: (
        -h["hits"], SEV_RANK.get(str(h["row"].get("severidad") or "").lower(), 3),
        -(h["row"].get("frecuencia") or 0), h["row"]["codigo"]))[:cfg["max_results"]]
    entries, redactions, dropped = [], 0, 0
    for item in ranked:
        row = item["row"]
        entry, hits = {}, 0
        for field in CONTENT_FIELDS:            # never evidencia or other columns
            value = row.get(field)
            if field == "frecuencia":
                entry[field] = value if isinstance(value, int) else None
                continue
            entry[field], n = sanitize(value)
            hits += n
        if not re.fullmatch(r"[\w.:-]{1,120}", entry["codigo"]):
            dropped += 1
            continue
        if hits and hits >= 4:
            dropped += 1                       # mostly sensitive: never published
            continue
        redactions += hits
        entries.append(entry)
    return {"schema_version": "LF_ROUTE_EKB_LOOKUP_V1", "terms": clean_terms,
            "entries": entries, "redactions": redactions, "dropped": dropped}


def to_markdown(result: dict) -> str:
    lines = ["# Errores conocidos (EKB) para este lote", "",
             "Consultado por la ruta antes de implementar (T56). Revisa cada uno: "
             "si tu cambio puede repetirlo, aplica la prevención y deja la validación como prueba.", ""]
    if not result["entries"]:
        lines.append("Sin coincidencias en el EKB para: " + ", ".join(result["terms"]) + ".")
    for e in result["entries"]:
        lines += [f"## {e['codigo']} — {e['titulo'] or '(sin título)'}",
                  f"- Severidad: {e['severidad'] or '-'} · Frecuencia: {e['frecuencia'] or '-'} · Categoría: {e['categoria'] or '-'}",
                  f"- Patrón: {e['patron'] or '-'}",
                  f"- Causa raíz: {e['causa_raiz'] or '-'}",
                  f"- Prevención: {e['prevencion'] or '-'}",
                  f"- Validación: {e['validacion'] or '-'}", ""]
    return "\n".join(lines).rstrip() + "\n"


def validate_entry(entry: dict, cfg: dict) -> dict:
    if not isinstance(entry, dict):
        raise EkbError("ROUTE_EKB_ENTRY_INVALID")
    allowed = {"codigo", "categoria", "severidad", "lifecycle_phase", "consumer_role",
               "root_cause_family", "detectability", "evidencia", "lote_origen", "pr", *WRITE_TEXT}
    extra = set(entry) - allowed
    if extra:
        raise EkbError("ROUTE_EKB_ENTRY_FIELD:" + sorted(extra)[0])
    if not (isinstance(entry.get("codigo"), str) and CODE.fullmatch(entry["codigo"])):
        raise EkbError("ROUTE_EKB_ENTRY_CODE")
    if entry.get("severidad") not in SEVERITIES:
        raise EkbError("ROUTE_EKB_ENTRY_SEVERITY")
    if not (isinstance(entry.get("categoria"), str) and re.fullmatch(r"[A-Z][A-Z0-9_]{2,40}", entry["categoria"])):
        raise EkbError("ROUTE_EKB_ENTRY_CATEGORY")
    for field, catalogue in (("root_cause_family", ROOT_CAUSES), ("detectability", DETECTABILITY),
                             ("lifecycle_phase", PHASES)):
        if entry.get(field) not in catalogue:
            raise EkbError("ROUTE_EKB_ENTRY_CATALOGUE:" + field)
    roles = entry.get("consumer_role")
    if not (isinstance(roles, list) and roles and len(set(roles)) == len(roles)
            and all(r in ROLES for r in roles)):
        raise EkbError("ROUTE_EKB_ENTRY_CATALOGUE:consumer_role")
    for field in WRITE_TEXT:
        value = entry.get(field)
        if not (isinstance(value, str) and 3 <= len(value.strip()) <= MAX_TEXT):
            raise EkbError("ROUTE_EKB_ENTRY_TEXT:" + field)
        if not is_clean(value):
            raise EkbError("ROUTE_EKB_ENTRY_SENSITIVE:" + field)
    # Evidence is a *reference* only (PR, run, CHG, lote), never logs or data.
    if not (isinstance(entry.get("evidencia"), str) and EVIDENCE_REF.fullmatch(entry["evidencia"])):
        raise EkbError("ROUTE_EKB_ENTRY_EVIDENCE")
    for field, pattern in (("lote_origen", r"[\w.-]{1,80}"), ("pr", r"#?\d{1,7}")):
        if field in entry and not (isinstance(entry[field], str) and re.fullmatch(pattern, entry[field])):
            raise EkbError("ROUTE_EKB_ENTRY_FIELD:" + field)
    # The route can only ever write its own rows.
    return {**entry, "source_context": cfg["source_context"], "source_ref": cfg["source_ref"]}


def register(entry: dict, *, execution_id: str, cfg: dict | None = None, env: dict | None = None,
             psql: str = "psql") -> dict:
    cfg = cfg or load_config()
    if not (isinstance(execution_id, str) and EXECUTION_ID.fullmatch(execution_id)):
        raise EkbError("ROUTE_EKB_EXECUTION_ID")
    payload = validate_entry(entry, cfg)
    env = dict(os.environ if env is None else env)
    script = f"select {cfg['writer_function']}(:'op', :'payload'::jsonb, :'exec')::text;\n"
    out = _psql(_url(env, cfg["write_secret"]), script,
                {"op": cfg["operation_code"], "exec": execution_id,
                 "payload": json.dumps(payload, ensure_ascii=False, sort_keys=True)}, psql, env)
    try:
        receipt = json.loads(out.strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise EkbError("ROUTE_EKB_UNAVAILABLE:SHAPE") from None
    if not (isinstance(receipt, dict) and receipt.get("classification") in ("NEW_ERROR", "RECURRENCE")
            and receipt.get("error_code") == payload["codigo"]):
        raise EkbError("ROUTE_EKB_UNAVAILABLE:SHAPE")
    return {"status": receipt["classification"], "codigo": payload["codigo"],
            "frequency_after": receipt.get("frequency_after"), "event_id": receipt.get("event_id")}


def load_catalog(path: Path = CATALOG) -> dict[str, dict]:
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        raise EkbError("ROUTE_EKB_CATALOG_INVALID") from None
    entries = data.get("entries") if data.get("schema_version") == "LF_ROUTE_ERROR_CATALOG_V1" else None
    if not isinstance(entries, dict) or not all(ROUTE_CODE.fullmatch(k) for k in entries):
        raise EkbError("ROUTE_EKB_CATALOG_INVALID")
    return entries


def catalog_entry(code: str, *, run_id: int, request: str | None, cfg: dict,
                  catalog: dict | None = None) -> dict | None:
    catalog = load_catalog() if catalog is None else catalog
    if code not in catalog:
        return None
    entry = {**catalog[code], "codigo": "LF-ROUTE-" + code.replace("_", "-"),
             "evidencia": f"run {run_id}" + (f"; lote {request}" if request else "")}
    if request:
        entry["lote_origen"] = request
    validate_entry(entry, cfg)
    return entry


def record(candidates: list[dict], *, execution_id: str, cfg: dict | None = None,
           env: dict | None = None, psql: str = "psql") -> list[dict]:
    """Register catalogued route failures; never raises (observability only)."""
    cfg = cfg or load_config()
    env = dict(os.environ if env is None else env)
    out = []
    try:
        catalog = load_catalog()
    except EkbError as exc:
        return [{"status": "SKIPPED", "reason": str(exc)}]
    for cand in candidates[:20]:
        cand = cand if isinstance(cand, dict) else {}
        code, run_id, request = cand.get("code"), cand.get("run_id"), cand.get("request")
        if not (isinstance(code, str) and ROUTE_CODE.fullmatch(code)
                and isinstance(run_id, int) and not isinstance(run_id, bool) and 0 < run_id < 10**14
                and (request is None or (isinstance(request, str)
                                         and re.fullmatch(r"req-[1-9][0-9]{0,6}", request)))):
            out.append({"status": "SKIPPED", "reason": "ROUTE_EKB_CANDIDATE_INVALID"})
            continue
        try:
            entry = catalog_entry(code, run_id=run_id, request=request, cfg=cfg, catalog=catalog)
            if entry is None:
                out.append({"status": "UNCATALOGUED", "code": code})
                continue
            out.append(register(entry, execution_id=execution_id, cfg=cfg, env=env, psql=psql))
        except EkbError as exc:
            out.append({"status": "SKIPPED", "code": code, "reason": str(exc)})
    return out


def lot_terms(area: str, skill_codes: list[str], paths: list[str]) -> list[str]:
    """Terms that describe a lot: its skills and its path stems (area is added by lookup)."""
    stems: list[str] = []
    generic = {"main", "java", "test", "tests", "src", "resources", "com", "sbx", "json",
               "app", "apps", "lib", "index", "spec", "tsx", "jsx"}
    for path in paths:
        # The top directory names the component, not the problem: skip it.
        for part in re.split(r"[._-]+|/", path.split("/", 1)[-1]):
            low = part.lower()
            if len(low) >= 4 and low not in stems and not low.isdigit() and low not in generic:
                stems.append(low)
    skills = [c for c in skill_codes if isinstance(c, str) and TERM.fullmatch(c)]
    return sorted(set(skills[:8] + stems[:8]))


def context_for_lot(area: str, skill_codes: list[str], paths: list[str], *,
                    env: dict | None = None, psql: str = "psql") -> tuple[bytes | None, str]:
    """Never blocks the route: no secret / no match / EKB down -> no ekb.md."""
    env = dict(os.environ if env is None else env)
    if not env.get(load_config()["read_secret"], "").strip():
        return None, "EKB_CONTEXT_SKIPPED:SECRET_MISSING"
    try:
        result = lookup(lot_terms(area, skill_codes, paths), area=area, env=env, psql=psql)
    except EkbError as exc:
        return None, "EKB_CONTEXT_SKIPPED:" + str(exc)
    if not result["entries"]:
        return None, "EKB_CONTEXT_EMPTY"
    text = to_markdown(result)
    if not all(is_clean(line) for line in text.splitlines()):
        return None, "EKB_CONTEXT_SKIPPED:UNSANITISED"   # defence in depth
    raw = text.encode("utf-8")
    if len(raw) > 64_000:
        return None, "EKB_CONTEXT_SKIPPED:TOO_LARGE"
    return raw, "EKB_CONTEXT_ADDED:" + str(len(result["entries"]))


def probe(*, cfg: dict | None = None, env: dict | None = None, psql: str = "psql") -> dict:
    """Connectivity and permission check for both secrets; never writes."""
    cfg = cfg or load_config()
    env = dict(os.environ if env is None else env)
    read = lookup(["LF-ROUTE"], cfg=cfg, env=env, psql=psql)
    script = ("begin transaction read only;\n"
              f"select has_function_privilege(current_user, '{cfg['writer_function']}(text, jsonb, text)', 'execute');\n"
              "rollback;\n")
    out = _psql(_url(env, cfg["write_secret"]), script, {}, psql, env)
    can_write = [x.strip() for x in out.splitlines() if x.strip() in ("t", "f")]
    if can_write != ["t"]:
        raise EkbError("ROUTE_EKB_UNAVAILABLE:WRITER_NOT_GRANTED")
    return {"read_ok": True, "route_rows": len(read["entries"]), "write_granted": True}


def _inside_repo(path: Path) -> bool:
    repo = Path(__file__).resolve().parents[2]
    try:
        path.resolve().relative_to(repo)
        return True
    except ValueError:
        return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    lk = sub.add_parser("lookup")
    lk.add_argument("--term", action="append", default=[])
    lk.add_argument("--area")
    lk.add_argument("--out", required=True, help="markdown file outside the repo checkout")
    lk.add_argument("--allow-missing", action="store_true",
                    help="secret absent → empty context instead of BLOCKED")
    sub.add_parser("probe")
    rc = sub.add_parser("record")
    rc.add_argument("--candidates", required=True, help="JSONL from the failure watchdog")
    rg = sub.add_parser("register")
    rg.add_argument("--entry", required=True, help="JSON file with the new route error")
    rg.add_argument("--execution-id", required=True, help="gha-<run_id>-<attempt>")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "lookup":
            out = Path(a.out)
            if _inside_repo(out):
                raise EkbError("ROUTE_EKB_OUT_INSIDE_REPO")
            try:
                result = lookup(a.term, area=a.area)
            except EkbError as exc:
                if not (a.allow_missing and str(exc) == "ROUTE_EKB_UNAVAILABLE:SECRET_MISSING"):
                    raise
                result = {"schema_version": "LF_ROUTE_EKB_LOOKUP_V1", "terms": [], "entries": [],
                          "redactions": 0, "dropped": 0, "unavailable": "SECRET_MISSING"}
            out.write_text(to_markdown(result), "utf-8")
            print(json.dumps({"status": "EKB_LOOKUP", "matches": len(result["entries"]),
                              "codes": [e["codigo"] for e in result["entries"]],
                              "redactions": result["redactions"], "dropped": result["dropped"],
                              **({"unavailable": result["unavailable"]} if "unavailable" in result else {})}))
        elif a.cmd == "record":
            path = Path(a.candidates)
            rows = []
            if path.is_file() and not path.is_symlink():
                for line in path.read_text("utf-8").splitlines()[:20]:
                    try:
                        rows.append(json.loads(line))
                    except ValueError:
                        rows.append({})
            run = os.environ.get("GITHUB_RUN_ID", "")
            attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
            for result in record(rows, execution_id=f"gha-{run}-{attempt}"):
                print(json.dumps(result))
            return 0
        elif a.cmd == "probe":
            print(json.dumps({"status": "EKB_PROBE_OK", **probe()}))
        else:
            try:
                entry = json.loads(Path(a.entry).read_text("utf-8"))
            except (OSError, ValueError):
                raise EkbError("ROUTE_EKB_ENTRY_INVALID") from None
            print(json.dumps({"result": "EKB_REGISTERED", **register(entry, execution_id=a.execution_id)}))
    except EkbError as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
