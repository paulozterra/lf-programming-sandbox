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
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
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
    ("*_SPEC.md", "MANUAL_CONTRACT", "Contrato/especificación escrita a mano"),
    ("contracts/*.openapi.yaml", "MANUAL_CONTRACT",
     "OpenAPI escrito a mano fuera de la ruta gobernada"),
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
    # Shared implementation ledger is generated by CP3.6, not by an owner.
    # Include its commits so the audit records the bot's work as AUTOMATIC,
    # rather than silently omitting the automatic registry publication.
    paths = [f"pilot/runs/{p}/", f"pilot/orchestrator/chain_plans/{p}.json",
             "pilot/registry/implemented.json"] + write_paths(p, tasks, rev)
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
    if path == f"pilot/runs/{p}/request_meta.json" and who == "BOT":
        return "AUTOMATIC", "REQUEST_PROVENANCE", "Procedencia del issue registrada por el bot"
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
    requester = None
    try:
        meta = json.loads(git("show", f"{rev}:pilot/runs/{p}/request_meta.json"))
        if (p == f"req-{meta['issue']}" and
                isinstance(meta["author"], str) and meta["author"]):
            requester = meta["author"]
    except (subprocess.CalledProcessError, ValueError, KeyError, TypeError):
        pass
    for sha, name, email, subject in commits:
        who = actor(email, name)
        # every file of an in-scope commit counts (base prep, tests, contracts...)
        for path in git("show", "--no-renames", "--name-only", "--format=", sha).split():
            verdict, code, desc = classify(path, who, p)
            if verdict == "IGNORED":
                continue
            row = {"commit": sha[:12], "actor": who, "subject": subject[:120], "path": path,
                   "verdict": verdict, "code": code, "description": desc}
            if path == f"pilot/runs/{p}/request.md" and who == "BOT" and requester:
                row["requester"] = requester
            rows.append(row)
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


# The exercise is identified by the existing T9 intake merge, not a second
# registry.  Git history provides the original baseline even after main moves.
# These are control-plane source paths, not generated per-request data.
_CONTROL_ROOTS = (".github/", ".lf/", "pilot/", "analysis/", "standards/", "vendor/")
_DYNAMIC_ROOTS = (
    ".lf/worker-context/", "pilot/runs/", "pilot/holdouts/",
    "pilot/native_proposals/", "pilot/worker_v08/native_tasks/",
    "pilot/orchestrator/chain_plans/", "pilot/orchestrator/evidence_inputs/",
    "standards/changes/", "pilot/worker_v08/examiner_defects/",
    "pilot/worker_v08/intake_defects/", "pilot/worker_v08/route_tool_defects/",
    "pilot/worker_v08/route_migrations/",
)
_DYNAMIC_FILES = {
    "pilot/registry/implemented.json", "standards/CAMBIOS.md",
    "pilot/orchestrator/request_lifecycle_control.json",
    "pilot/orchestrator/lot_recovery.json",
    "pilot/worker_v08/native_format_activation.json",
}
_CONTROL_FILES = {".gitignore", ".editorconfig", "CLAUDE.md"}
_SHA40 = re.compile(r"[0-9a-f]{40}\Z")
_SHA64 = re.compile(r"[0-9a-f]{64}\Z")


def _control_path(path):
    return ((path.startswith(_CONTROL_ROOTS) or path in _CONTROL_FILES)
            and not path.startswith(_DYNAMIC_ROOTS)
            and path not in _DYNAMIC_FILES)


def _history_paths(start, end, paths):
    """First-parent deltas, including transient changes later reverted.
    Never read the contents of encrypted exams, private references or proposals.
    """
    from pilot.audit.historical_evidence import git as git_bytes
    raw = git_bytes(ROOT, "log", "--first-parent", "--diff-merges=first-parent",
                    "--format=%x1e%H", "--name-only", "-z", "--no-renames",
                    start + ".." + end, "--", *paths)
    for record in raw.split(b"\x1e"):
        if not record:
            continue
        head, sep, names = record.partition(b"\0")
        if not sep or not _SHA40.fullmatch(head.decode("ascii")):
            raise ValueError("F1C_HISTORY_UNRESOLVED")
        yield head.decode("ascii"), [x.decode("utf-8") for x in
                                     names.lstrip(b"\n").split(b"\0") if x]


def _control_digest(rev):
    from pilot.audit.historical_evidence import git as git_bytes
    rows = []
    for entry in git_bytes(ROOT, "ls-tree", "-r", "-z", rev).split(b"\0"):
        if not entry:
            continue
        meta, sep, name = entry.partition(b"\t")
        path = name.decode("utf-8")
        if not sep:
            raise ValueError("F1C_TREE_UNRESOLVED")
        if _control_path(path):
            rows.append(entry)
    if not rows:
        raise ValueError("F1C_CONTROL_TREE_UNRESOLVED")
    # Includes path, Git blob/tree identity and mode, not mutable worktree data.
    return hashlib.sha256(b"\0".join(rows)).hexdigest()


def _intake(p, rev, history):
    """Recover the original T9 intake and its first parent from trusted history."""
    from pilot.audit.historical_evidence import tree_blob
    from pilot.orchestrator.issue_intake import metadata
    path = f"pilot/runs/{p}/request.md"
    meta_path = f"pilot/runs/{p}/request_meta.json"
    candidates = git("log", "--first-parent", "--diff-merges=first-parent",
                     "--diff-filter=A", "--format=%H", "--name-only", rev,
                     "--", path).splitlines()
    adds = [v for v in candidates if _SHA40.fullmatch(v)]
    if len(adds) != 1 or adds[0] not in history:
        raise ValueError("F1C_INTAKE_UNRESOLVED")
    intake = adds[0]
    parents = git("show", "-s", "--format=%P", intake).split()
    title = git("show", "-s", "--format=%s", intake).strip()
    if len(parents) != 2 or not re.fullmatch(r"Merge PR #[1-9][0-9]* via sandbox-train", title):
        raise ValueError("F1C_INTAKE_NOT_TRAIN")
    base, head = parents
    expected = {path, meta_path}
    if (set(git("diff", "--name-only", base, intake).splitlines()) != expected
            or any(tree_blob(ROOT, base, name, optional=True) is not None
                   for name in expected)):
        raise ValueError("F1C_INTAKE_SCOPE_DRIFT")
    raw = {name: tree_blob(ROOT, intake, name) for name in expected}
    if (any(tree_blob(ROOT, head, name) != value for name, value in raw.items())
            or git("log", "-1", "--format=%ae", head, "--", meta_path).strip() != BOT_EMAIL):
        raise ValueError("F1C_INTAKE_PROVENANCE_UNRESOLVED")
    from pilot.orchestrator.request_finalize import decode
    meta = decode(raw[meta_path])
    if (type(meta.get("issue")) is not int or meta["issue"] != int(p[4:])
            or metadata({"number": meta["issue"], "user": {"login": meta.get("author")},
                         "created_at": meta.get("date")}) != meta):
        raise ValueError("F1C_INTAKE_METADATA_INVALID")
    return intake, base, {name: hashlib.sha256(value).hexdigest()
                          for name, value in sorted(raw.items())}


def _task_conditions(p, rev, history_rows):
    """Read the first committed, complete package, not a later regenerated hash.
    New task identities are allowed; changes to already sealed inputs are not
    silently interpreted as the same evaluation.
    """
    from pilot.audit.historical_evidence import tree_blob, EvidenceError
    from pilot.orchestrator.task_pack_publication import paths_for, verify_published_pair
    import tempfile
    from pilot.orchestrator.native_submission_contract import canonical, proposal_submission_contract
    inputs, drift, missing = [], [], []
    tasks = set(tasks_of(p, rev))
    prefix = f"pilot/runs/{p}/proposal_requests/"
    # Discover retired tasks as well as the current plan. Do not read hidden
    # exams; public registration bytes already bind the independent exam.
    for _, paths in history_rows:
        for path in paths:
            match = re.fullmatch(re.escape(prefix) + r"([a-z][a-z0-9_-]{0,31})[.]task-pack[.]json", path)
            if match:
                tasks.add(match[1])
    for task in sorted(tasks):
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", task):
            missing.append("TASK_ID_UNRESOLVED")
            continue
        pack, meta = paths_for(p, task)
        reg = f"pilot/worker_v08/native_tasks/{task}.json"
        context = f".lf/worker-context/{task}/"
        # The first *published package* is the seal boundary, not the
        # registration draft (which intentionally changes before export).
        versions = [sha for sha, paths in reversed(history_rows) if pack in paths]
        if not versions:
            missing.append(task + ":TASK_PACK_UNAVAILABLE")
            continue
        sealed = versions[0]
        try:
            parents = git("show", "-s", "--format=%P", sealed).split()
            if (len(parents) != 2 or not re.fullmatch(r"Merge PR #[1-9][0-9]* via sandbox-train",
                    git("show", "-s", "--format=%s", sealed).strip())
                    or git("log", "-1", "--format=%ae", parents[1], "--", pack).strip() != BOT_EMAIL):
                raise ValueError("F1C_PACK_PUBLICATION_UNRESOLVED")
            raw = {path: tree_blob(ROOT, sealed, path) for path in (pack, meta, reg)}
            if any(tree_blob(ROOT, parents[1], path) != raw[path] for path in raw):
                raise ValueError("F1C_PACK_PUBLICATION_UNRESOLVED")
            from pilot.orchestrator.request_finalize import decode
            companion, registration = decode(raw[meta]), decode(raw[reg])
            spec = registration["task_spec"]
            base = spec["base_head_sha"]
            pack_sha = companion["task_pack_sha256"]
            if (not _SHA40.fullmatch(base) or not _SHA64.fullmatch(spec["source_snapshot_sha256"])
                    or companion.get("base_head_sha") != base or spec.get("task_id") != "LF-WORKER-NATIVE-" + task.upper()
                    or not _SHA64.fullmatch(registration["holdout_sha256"])
                    or type(spec.get("max_attempts")) is not int or spec["max_attempts"] != 1
                    or not isinstance(companion.get("lot_id"), str)):
                raise ValueError("F1C_TASK_BINDING_INVALID")
            expected_submission = proposal_submission_contract(task, spec)
            if "submission" in companion and companion["submission"] != expected_submission:
                raise ValueError("F1C_SUBMISSION_CONTRACT_DRIFT")
            # Reuse T18's actual pack/companion verification against immutable
            # public bytes; no checkout, no export, no model.
            with tempfile.TemporaryDirectory(prefix="lf-f1c-pack-") as tmp:
                for path in (pack, meta):
                    target = Path(tmp) / path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(raw[path])
                verify_published_pair(Path(tmp), p, task, pack_sha)
            # The sealed base need not itself be first-parent (CP3.4 commits
            # context on a preparation branch); it must be an ancestor.
            ancestor = subprocess.run(["git", "-C", str(ROOT), "merge-base",
                                       "--is-ancestor", base, sealed],
                                      capture_output=True, timeout=20)
            if ancestor.returncode == 1:
                raise ValueError("F1C_TASK_BASE_UNRESOLVED")
            ancestor.check_returncode()
            ctx_paths = git("ls-tree", "-r", "--name-only", base, "--", context).splitlines()
            if not {context + name for name in ("profile.md", "skills.md", "receipt.json")} <= set(ctx_paths):
                raise ValueError("F1C_TASK_CONTEXT_UNRESOLVED")
            ctx = {path: hashlib.sha256(tree_blob(ROOT, base, path)).hexdigest()
                   for path in ctx_paths}
            if (set(git("ls-tree", "-r", "--name-only", sealed, "--", context).splitlines()) != set(ctx)
                    or any(hashlib.sha256(tree_blob(ROOT, sealed, path)).hexdigest() != sha
                           for path, sha in ctx.items())):
                raise ValueError("F1C_TASK_CONTEXT_DRIFT")
            # Public registration hash binds the original exam without
            # exposing its oracle hash or reading any encrypted file.
            exam_meta = f"pilot/runs/{p}/claude_meta/{task}.json"
            # Read only public examiner metadata identity, not encrypted
            # holdout contents or their plaintext digests.
            from pilot.orchestrator.stale_exam import exam_paths
            exam_scope = set(exam_paths(p, task))
            exam_tree = git("ls-tree", "-r", "-z", sealed, "--", *sorted(exam_scope))
            exam_entries = {line.split("\t", 1)[1] for line in exam_tree.split("\0")
                            if line.startswith(("100644 blob ", "100755 blob ")) and "\t" in line}
            if not {exam_meta, f"pilot/holdouts/{task}.oracle.json.age"} <= exam_entries:
                raise ValueError("F1C_EXAM_PROVENANCE_UNRESOLVED")
            row = {"task_id": task, "lot_id": companion["lot_id"],
                   "worker_max_attempts": spec["max_attempts"],
                   "sealed_at": sealed, "base_head_sha": base,
                   "source_snapshot_sha256": spec["source_snapshot_sha256"],
                   "task_pack_sha256": pack_sha,
                   "registration_sha256": hashlib.sha256(raw[reg]).hexdigest(),
                   "acceptance_commands_sha256": hashlib.sha256(canonical(spec["acceptance_commands"])).hexdigest(),
                   "exam_tree_sha256": hashlib.sha256(exam_tree.encode("utf-8")).hexdigest(),
                   "context_sha256": hashlib.sha256(canonical(ctx)).hexdigest()}
            inputs.append(row)
            seen = False
            for sha, paths in reversed(history_rows):
                if sha == sealed:
                    seen = True
                    continue
                if not seen:
                    continue
                affected = sorted(path for path in paths if path in (pack, reg)
                                  or path in exam_scope or path.startswith(context)
                                  or path.startswith(f"pilot/runs/{p}/templates/{task}.")
                                  or any(path.startswith(prefix + task + ".") for prefix in
                                         ("pilot/worker_v08/route_migrations/",
                                          "pilot/worker_v08/route_tool_defects/",
                                          "pilot/worker_v08/examiner_defects/",
                                          "pilot/worker_v08/intake_defects/")))
                # T18 may recover the exact same pair and T19 enrich public
                # submission instructions. Neither changes the frozen inputs.
                if meta in paths:
                    current = tree_blob(ROOT, sha, meta, optional=True)
                    if current is None:
                        affected.append(meta)
                    else:
                        previous = {k: v for k, v in companion.items() if k != "submission"}
                        updated = decode(current)
                        new = {k: v for k, v in updated.items() if k != "submission"}
                        if (previous != new or ("submission" in updated
                                               and updated["submission"] != expected_submission)):
                            affected.append(meta)
                if affected:
                    drift.append({"commit": sha, "paths": sorted(affected)})
        except EvidenceError as exc:
            if str(exc) == "AUDIT_PROVENANCE:GIT_UNRESOLVED":
                raise RuntimeError("F1C_GIT_UNAVAILABLE") from exc
            missing.append(task + ":TASK_SEAL_UNRESOLVED")
        except (ValueError, KeyError, TypeError, AttributeError, UnicodeError):
            missing.append(task + ":TASK_SEAL_UNRESOLVED")
    return inputs, drift, missing


def _scoped_policy(p, tasks, rev, path):
    from pilot.audit.historical_evidence import tree_blob
    from pilot.orchestrator.request_finalize import decode
    raw = tree_blob(ROOT, rev, path, optional=True)
    if raw is None:
        return None
    if path.endswith("/lot_recovery.json"):
        from pilot.orchestrator.lot_recovery import parse
        return [v for (request, _), v in sorted(parse(raw).items()) if request == p]
    if path.endswith("/request_lifecycle_control.json"):
        from pilot.orchestrator.request_lifecycle import parse_control
        return parse_control(raw).get(p)
    data = decode(raw)
    if (not isinstance(data, dict) or set(data) != {"schema_version", "tasks"}
            or data["schema_version"] != "LF_NATIVE_FORMAT_ACTIVATION_V1"
            or not isinstance(data["tasks"], dict)):
        raise ValueError("F1C_FORMAT_POLICY_UNRESOLVED")
    return {task: data["tasks"][task] for task in sorted(tasks) if task in data["tasks"]}


def _exercise_end(p, rev, rows):
    from pilot.audit.historical_evidence import tree_blob, EvidenceError
    from pilot.orchestrator.request_finalize import terminal_outcome, FinalizationError

    class HistoricalView:
        def __init__(self, revision):
            self.revision = revision

        def read(self, path):
            try:
                return tree_blob(ROOT, self.revision, path, optional=True)
            except EvidenceError as exc:
                if str(exc) == "AUDIT_PROVENANCE:GIT_UNRESOLVED":
                    raise RuntimeError("F1C_GIT_UNAVAILABLE") from exc
                raise

    outcome = terminal_outcome(HistoricalView(rev), p)
    if outcome is None:
        return rev, rows, []
    folder = f"pilot/runs/{p}/"
    chronological = list(reversed(rows))
    for index, (sha, paths) in enumerate(chronological):
        if not any(path == "pilot/registry/implemented.json"
                   or path.startswith(folder + "evidence/")
                   or path in {folder + "state.json", folder + "lots.json",
                               folder + "H_REPORT.md"} for path in paths):
            continue
        try:
            historical = terminal_outcome(HistoricalView(sha), p)
        except FinalizationError:
            continue
        if historical == outcome:
            # Same receipt fingerprint; later route maintenance is outside this
            # exercise. A changed terminal receipt is not accepted as the same one.
            from pilot.orchestrator.request_finalize import evidence_records
            records = evidence_records(HistoricalView(sha), p, outcome["planned"], outcome["merged"])
            return sha, list(reversed(chronological[:index+1])), records
        if historical is not None:
            raise ValueError("F1C_TERMINAL_PROOF_DRIFT")
    raise ValueError("F1C_TERMINAL_BOUNDARY_UNRESOLVED")


def exercise_conditions(p, rev):
    """F1.C evidence-only projection in T0; never a lifecycle/Worker gate.

    A condition change invalidates autonomous evaluation, not the legitimate
    implementation or automatic recovery of the request. F6 remains the
    certification authority; this report never grants it.
    """
    from pilot.audit.historical_evidence import EvidenceError, tree_blob
    result = {"status": "UNRESOLVED", "autonomy_certified": False,
              "request_id": p, "drift": [], "missing": []}
    if not re.fullmatch(r"req-[1-9][0-9]*", p):
        return dict(result, status="LEGACY_UNACCREDITED")
    try:
        rev = git("rev-parse", "--verify", rev + "^{commit}").strip()
        remote = subprocess.run(["git", "-C", str(ROOT), "show-ref", "--verify",
                                 "--quiet", "refs/remotes/origin/main"],
                                capture_output=True, timeout=20)
        if remote.returncode == 1:
            raise ValueError("F1C_TRUSTED_MAIN_UNAVAILABLE")
        remote.check_returncode()
        main = git("rev-parse", "--verify", "refs/remotes/origin/main^{commit}").strip()
        if git("rev-parse", "--is-shallow-repository").strip() != "false":
            raise ValueError("F1C_HISTORY_SHALLOW")
        history = git("rev-list", "--first-parent", main).splitlines()
        if rev not in history:
            raise ValueError("F1C_REVISION_NOT_MAIN_HISTORY")
        intake, base, input_hashes = _intake(p, rev, history)
        result.update(intake_merge_sha=intake, baseline_head_sha=base,
                      baseline_tree_sha=git("rev-parse", base + "^{tree}").strip(),
                      route_sha256=_control_digest(base), request_input_sha256=input_hashes,
                      exercise_id=p + "@" + intake)
        rows = list(_history_paths(intake, rev, (".github", ".lf", "pilot", "analysis",
                                                 "standards", "vendor", *_CONTROL_FILES)))
        rev, rows, evidence = _exercise_end(p, rev, rows)
        result["exercise_end_sha"] = rev
        fixed = set(input_hashes)
        # Analysis and lots are generated only after intake: freeze the first
        # committed version, not an invented value at the start of the request.
        required = {f"pilot/runs/{p}/{name}" for name in ("analysis.json", "lots.json")}
        generated = required | {f"pilot/runs/{p}/{name}" for name in
                                ("chain_plan.json", "reuse_assessment.json", "atomized_inputs.json")}
        generated.add(f"pilot/orchestrator/chain_plans/{p}.json")
        first = {}
        for sha, paths in reversed(rows):
            changed = []
            for path in paths:
                if _control_path(path) or path in fixed:
                    changed.append(path)
                elif path in generated:
                    if path in first:
                        changed.append(path)
                    else:
                        raw = tree_blob(ROOT, sha, path, optional=True)
                        if raw is None:
                            raise ValueError("F1C_INPUT_PROVENANCE_UNRESOLVED")
                        first[path] = {"commit": sha, "sha256": hashlib.sha256(raw).hexdigest()}
            if changed:
                result["drift"].append({"commit": sha, "paths": sorted(changed)})
        result["generated_inputs"] = first
        if not required <= set(first):
            result["missing"].append("ANALYSIS_OR_LOTS_UNAVAILABLE")
        tasks, task_drift, missing = _task_conditions(p, rev, rows)
        result.update(task_seals=tasks)
        result["drift"].extend(task_drift)
        result["missing"].extend(missing)
        task_names = {t["task_id"] for t in tasks} | set(tasks_of(p, rev))
        scoped = sorted(path for path in _DYNAMIC_FILES if path.endswith(
            ("lot_recovery.json", "request_lifecycle_control.json", "native_format_activation.json")))
        policies = {path: _scoped_policy(p, task_names, intake, path) for path in scoped}
        result["initial_scoped_policies"] = dict(policies)
        for sha, paths in reversed(rows):
            for path in set(paths) & set(scoped):
                observed = _scoped_policy(p, task_names, sha, path)
                if observed != policies[path]:
                    result["drift"].append({"commit": sha, "paths": [path]})
                    policies[path] = observed
        if not tasks:
            result["missing"].append("NO_SEALED_TASK")
        result["observed_revision"] = rev
        result["observed_route_sha256"] = _control_digest(rev)
        if result["route_sha256"] != result["observed_route_sha256"] and not any(
                _control_path(path) for row in result["drift"] for path in row["paths"]):
            raise ValueError("F1C_CONTROL_HISTORY_INCOMPLETE")
        # PG06 build/lint observations are distinct from a Git tree identity.
        # Neither the existing C1 producer nor an unauthenticated C4 candidate
        # constitutes a verified baseline execution receipt.
        result["pg06_baseline_status"] = "BASELINE_EXECUTION_NOT_ATTESTED"
        result["pg06_candidates"] = []
        from pilot.orchestrator.pg37_evidence import digest
        for record in evidence:
            stage = record["stages"]["PG-06"]
            payload = stage.get("evidence", {})
            candidate = payload.get("baseline_candidate") if isinstance(payload, dict) else None
            if candidate is None:
                continue
            if (not isinstance(candidate, dict)
                    or candidate.get("schema_version") != "PG06_C4_BASELINE_BUILD_LINT_CANDIDATE_V1"
                    or stage.get("evidence_sha256") != digest(payload)
                    or candidate.get("production_authority") is not False
                    or candidate.get("receipts_authenticated") is not False
                    or candidate.get("unchanged_target_verified") is not False):
                result["missing"].append("F1C_PG06_CANDIDATE_UNRESOLVED")
                continue
            # Do not trust a caller-supplied candidate checksum or a later HEAD.
            from pilot.lf_producers_pinned.pg06_preflight_candidate.tools.pg06_c4_baseline_capture_candidate_v1 import _digest as pg06_digest
            target = candidate.get("target_binding", {})
            allowed = {base, intake} | {seal["base_head_sha"] for seal in tasks
                                       if seal["lot_id"] == record["lot_id"]}
            if (not isinstance(target, dict)
                    or target.get("repo_full_name") != "paulozterra/lf-programming-sandbox"
                    or target.get("base_head_sha") not in allowed
                    or candidate.get("candidate_sha256") != pg06_digest(
                        {k:v for k,v in candidate.items() if k != "candidate_sha256"})):
                result["missing"].append("F1C_PG06_BASELINE_BINDING_UNRESOLVED")
                continue
            result["pg06_candidates"].append({
                "lot_id": record["lot_id"], "merge_sha": record["merge_sha"],
                "base_head_sha": target["base_head_sha"],
                "candidate_sha256": candidate["candidate_sha256"],
                "baseline_digest": candidate["baseline_digest_recorded"],
                "receipts_authenticated": False})
        if result["pg06_candidates"]:
            result["pg06_baseline_status"] = "CANDIDATE_RECORDED_EXECUTION_NOT_ATTESTED"
        result["status"] = ("INVALIDATED_CONDITION_DRIFT" if result["drift"]
                            else "CONDITIONS_UNRESOLVED" if result["missing"]
                            else "GIT_CONDITIONS_BOUND_BASELINE_UNATTESTED")
    except EvidenceError as exc:
        if str(exc) == "AUDIT_PROVENANCE:GIT_UNRESOLVED":
            raise RuntimeError("F1C_GIT_UNAVAILABLE") from exc
        result["missing"].append("F1C_PROVENANCE_UNRESOLVED")
        if result["drift"]:
            result["status"] = "INVALIDATED_CONDITION_DRIFT"
    except (ValueError, KeyError, TypeError, AttributeError, UnicodeError) as exc:
        code = str(exc)
        result["missing"].append(code if re.fullmatch(r"F1C_[A-Z_]+", code)
                                 else "F1C_PROVENANCE_UNRESOLVED")
        if result["drift"]:
            result["status"] = "INVALIDATED_CONDITION_DRIFT"
    return result


def report(p: str, rev: str = "HEAD", with_labels: bool = True) -> dict:
    if not SLUG.fullmatch(p):
        raise SystemExit("REQUEST_ID_INVALID")
    rev = git("rev-parse", "--verify", rev + "^{commit}").strip()
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
        "exercise_conditions": exercise_conditions(p, rev),
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
    freeze = r.get("exercise_conditions")
    if freeze is not None:
        lines += ["## Condiciones del ejercicio (F1.C)", "",
                  f"**{freeze['status']}** — no constituye certificación autónoma.", "",
                  f"Intake: `{freeze.get('intake_merge_sha', 'NO_ACREDITADO')}`",
                  f"Baseline Git: `{freeze.get('baseline_head_sha', 'NO_ACREDITADO')}`",
                  f"Árbol baseline: `{freeze.get('baseline_tree_sha', 'NO_ACREDITADO')}`",
                  f"Versión de ruta: `{freeze.get('route_sha256', 'NO_ACREDITADA')}`",
                  f"PG06: {freeze.get('pg06_baseline_status', 'NO_ACREDITADO')}", ""]
        for path, digest in sorted(freeze.get("request_input_sha256", {}).items()):
            lines.append(f"- Entrada `{path}`: `{digest}`")
        for path, item in sorted(freeze.get("generated_inputs", {}).items()):
            lines.append(f"- Entrada generada `{path}` @ `{item['commit']}`: `{item['sha256']}`")
        for path, policy in sorted(freeze.get("initial_scoped_policies", {}).items()):
            lines.append(f"- Política inicial `{path}`: " + json.dumps(policy, sort_keys=True, ensure_ascii=True))
        for seal in freeze.get("task_seals", []):
            lines.append("- Sello de tarea: " + json.dumps(seal, sort_keys=True, ensure_ascii=True))
        for baseline in freeze.get("pg06_candidates", []):
            lines.append("- PG06-C4: " + json.dumps(baseline, sort_keys=True, ensure_ascii=True))
        for item in freeze["drift"]:
            lines.append("- Drift en `" + item["commit"] + "`: " + ", ".join("`"+p+"`" for p in item["paths"]))
        for reason in freeze["missing"]:
            lines.append("- Evidencia pendiente: " + reason)
        lines.append("")
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
