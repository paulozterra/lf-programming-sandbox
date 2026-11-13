#!/usr/bin/env python3
"""T4 admission guards for governed native chain registration.

No model, oracle read, or hidden-test discovery. These checks execute on the
trusted main checkout, before prepare_native_lot.py is invoked.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

TASK = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
SHA = re.compile(r"[0-9a-f]{40}\Z")


class AdmissionBlocked(ValueError):
    """Machine-readable T4 registration blocker."""


def require_green_base(sha: str, fetch) -> None:
    """Require a successful ci.yml run on exactly this main commit.

    GitHub's combined commit status is not sufficient: this project executes
    its CI through Actions, including workflow_dispatch.
    """
    if not isinstance(sha, str) or not SHA.fullmatch(sha):
        raise AdmissionBlocked("BASE_NO_VERDE")
    payload = fetch("actions/workflows/ci.yml/runs?head_sha=" + sha + "&per_page=100")
    if not isinstance(payload, dict):
        raise AdmissionBlocked("BASE_NO_VERDE")
    runs = payload.get("workflow_runs")
    count = payload.get("total_count")
    if not isinstance(runs, list) or type(count) is not int or count > 100:
        raise AdmissionBlocked("BASE_NO_VERDE")
    eligible = [run for run in runs
                if isinstance(run, dict) and run.get("head_sha") == sha
                and run.get("head_branch") == "main"
                and run.get("event") in ("push", "workflow_dispatch")
                and type(run.get("run_attempt")) is int]
    if not eligible:
        raise AdmissionBlocked("BASE_NO_VERDE")
    latest = max(eligible, key=lambda run: (run.get("created_at") or "", run.get("id") or 0))
    if latest.get("status") != "completed" or latest.get("conclusion") != "success":
        raise AdmissionBlocked("BASE_NO_VERDE")


def missing_exam(root: Path, task: str) -> bool:
    """Inspect only the ciphertext path's existence, NEVER its contents."""
    if not isinstance(task, str) or not TASK.fullmatch(task):
        raise AdmissionBlocked("EXAMEN_PENDIENTE")
    path = root / "pilot" / "holdouts" / (task + ".oracle.json.age")
    if path.is_symlink():
        raise AdmissionBlocked("EXAMEN_PENDIENTE")
    return not path.is_file()


def public_exam_request(root: Path, request: str, binding: dict, lot: dict) -> tuple[str, str]:
    """Prepare only public request information; never embed oracle metadata."""
    task = binding["task_name"]
    if not TASK.fullmatch(task):
        raise AdmissionBlocked("EXAMEN_PENDIENTE")
    template = root / binding["template_path"]
    if template.is_symlink() or not template.is_file():
        raise AdmissionBlocked("EXAMEN_PENDIENTE")
    parsed = json.loads(template.read_text("utf-8"))
    spec = parsed.get("task_spec", {})
    if not isinstance(spec, dict):
        raise AdmissionBlocked("EXAMEN_PENDIENTE")
    scope = spec.get("write_path_patterns")
    if not isinstance(scope, list) or not scope or any(not isinstance(p, str) for p in scope):
        raise AdmissionBlocked("EXAMEN_PENDIENTE")
    # Use the authoritative public T2 skeleton when the lot references one.
    # Other areas still have a public task skeleton and REQ IDs in lots.json;
    # never guess a module or search encrypted examiner material.
    context = spec.get("context_path_patterns", [])
    skeleton_paths = [path for path in context if isinstance(path, str)
                      and re.fullmatch(r"contracts/[a-z0-9_-]+[.]skeleton[.]json", path)]
    requirements = lot.get("requirement_ids")
    if (not isinstance(requirements, list) or not requirements
            or any(not isinstance(r, str) or not r.startswith("REQ-") for r in requirements)):
        raise AdmissionBlocked("EXAMEN_PENDIENTE")
    if len(skeleton_paths) > 1:
        raise AdmissionBlocked("EXAMEN_PENDIENTE")
    public = {"schema_version": "T4_PUBLIC_TASK_SKELETON_V1",
              "area": lot.get("area"), "requirement_ids": requirements,
              "write_paths": scope}
    if skeleton_paths:
        skeleton_file = root / skeleton_paths[0]
        if skeleton_file.is_symlink() or not skeleton_file.is_file():
            raise AdmissionBlocked("EXAMEN_PENDIENTE")
        skeleton = json.loads(skeleton_file.read_text("utf-8"))
        if skeleton.get("schema_version") != "T2_CONTRACT_SKELETON_V1":
            raise AdmissionBlocked("EXAMEN_PENDIENTE")
        public = {key: skeleton[key] for key in ("schema_version", "functional_module",
                   "fields", "errors", "rules", "requirement_ids") if key in skeleton}
        if not set(requirements).issubset(set(public.get("requirement_ids", []))):
            raise AdmissionBlocked("EXAMEN_PENDIENTE")
    body = ("Solicitud automática de examen independiente (T4).\n\n"
            f"- Pedido: `{request}`\n- Lote: `{lot['id']}`\n"
            f"- Task ID: `{task}`\n"
            f"- Rutas de escritura: `{json.dumps(scope, ensure_ascii=False)}`\n"
            f"- REQ: `{json.dumps(requirements, ensure_ascii=False)}`\n"
            "- Esqueleto público:\n\n```json\n"
            + json.dumps(public, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n```\n\n"
            "El examinador independiente aporta el cifrado y su metadata. "
            "NO publicar claves ni resultados privados. "
            "La cadena permanece bloqueada con EXAMEN_PENDIENTE.")
    return "EXAM_REQUEST: " + task, body


def incremental_task(task: str, unavailable: set[str]) -> str:
    """Deterministically allocate an unused task suffix; never overwrite."""
    if not isinstance(task, str) or not TASK.fullmatch(task):
        raise AdmissionBlocked("TASK_INVALID")
    if task not in unavailable:
        return task
    for suffix in range(2, 1000):
        candidate = task + str(suffix)
        if TASK.fullmatch(candidate) and candidate not in unavailable:
            return candidate
    raise AdmissionBlocked("TASK_SUFFIX_EXHAUSTED")


def registration_variant(root: Path, base_task: str, template_path: str,
                         source_sha256: str) -> str | None:
    """Return a new task ID only when the newest registration is stale.

    None means an existing registration on main is still reusable. Suffixes
    are monotonic and tied to registration content; prior attempts are never
    overwritten or silently resealed. No examiner artifact is inspected.
    """
    import hashlib
    if not TASK.fullmatch(base_task) or not re.fullmatch(r"[0-9a-f]{64}", source_sha256):
        raise AdmissionBlocked("TASK_INVALID")
    directory = root / "pilot/worker_v08/native_tasks"
    if not directory.is_dir() or directory.is_symlink():
        raise AdmissionBlocked("TASK_DIRECTORY_INVALID")
    names = []
    for path in directory.iterdir():
        if (path.is_symlink() or not path.is_file() or path.suffix != ".json"):
            continue
        stem = path.stem
        if stem == base_task or (stem.startswith(base_task)
                and re.fullmatch(r"(?:[2-9]|[1-9][0-9]+)", stem[len(base_task):])):
            names.append(stem)
    if not names:
        return base_task
    def order(name):
        return 1 if name == base_task else int(name[len(base_task):])
    newest = max(names, key=order)
    record = json.loads((directory / (newest + ".json")).read_text("utf-8"))
    spec = record.get("task_spec")
    source = root / template_path
    if source.is_symlink() or not source.is_file() or not isinstance(spec, dict):
        raise AdmissionBlocked("TASK_REGISTRATION_INVALID")
    desired = json.loads(source.read_text("utf-8")).get("task_spec")
    if not isinstance(desired, dict):
        raise AdmissionBlocked("TASK_TEMPLATE_INVALID")
    tracked = ("objective", "write_path_patterns", "context_path_patterns",
               "protected_path_patterns", "acceptance_commands", "max_patch_bytes",
               "max_changed_files")
    same_pack = all(spec.get(k) == desired.get(k) for k in tracked)
    if same_pack and spec.get("source_snapshot_sha256") == source_sha256:
        return None
    return incremental_task(base_task, set(names))


# Explicit HTTP outcome assertions from existing protected Java tests. Do not
# interpret test names, comments, or free-form expectations as executable facts.
_HTTP_STATUS = {
    "Ok": 200, "Created": 201, "Accepted": 202, "NoContent": 204,
    "BadRequest": 400, "Unauthorized": 401, "Forbidden": 403,
    "NotFound": 404, "Conflict": 409, "UnprocessableEntity": 422,
    "InternalServerError": 500, "ServiceUnavailable": 503,
}
_ENDPOINT = re.compile(
    r"(?<!\w)(?P<method>get|post|put|patch|delete)\s*\(\s*"
    r'["\x27](?P<route>/[^"\x27]+)["\x27]', re.I)
_STATUS = re.compile(r"status\(\)\s*\.\s*is(?P<name>[A-Za-z]+)\(\)")
_TEST_TYPES = {".java", ".ts", ".tsx"}


def _route_matches(template: str, actual: str) -> bool:
    segments = []
    for part in template.split("/"):
        if part.startswith("{") and part.endswith("}"):
            segments.append(r"[^/]+")
        else:
            segments.append(re.escape(part))
    return re.fullmatch("/".join(segments), actual) is not None


def protected_test_conflict(root: Path, lot: dict, binding: dict) -> None:
    """Block only a demonstrable HTTP-status contradiction with a signed-in
    contract. Never rewrite an existing test; don't infer test semantics.

    If the contract isn't yet produced (CONTRATO lot), no comparison is
    possible at this stage. The native Worker still runs protected tests.
    """
    from fnmatch import fnmatch
    ref = lot.get("contract_context_ref")
    if not isinstance(ref, str) or not re.fullmatch(r"contracts/[a-z0-9_-]+[.]openapi[.]yaml", ref):
        return
    contract = root / ref
    if not contract.exists():
        return  # contract lot precedes its consumers
    if contract.is_symlink() or not contract.is_file():
        raise AdmissionBlocked("TEST_PROTEGIDO_EN_CONFLICTO")
    try:
        import yaml
        doc = yaml.safe_load(contract.read_text("utf-8"))
    except Exception as exc:
        raise AdmissionBlocked("TEST_PROTEGIDO_EN_CONFLICTO") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("paths"), dict):
        raise AdmissionBlocked("TEST_PROTEGIDO_EN_CONFLICTO")
    template = root / binding["template_path"]
    if template.is_symlink() or not template.is_file():
        raise AdmissionBlocked("TEST_PROTEGIDO_EN_CONFLICTO")
    spec = json.loads(template.read_text("utf-8")).get("task_spec", {})
    patterns = spec.get("protected_path_patterns", [])
    if not isinstance(patterns, list):
        raise AdmissionBlocked("TEST_PROTEGIDO_EN_CONFLICTO")
    roots = (root / "apps/time-service/src/test", root / "frontend/src")
    for folder in roots:
        if not folder.is_dir() or folder.is_symlink():
            continue
        for file in sorted(folder.rglob("*")):
            if not file.is_file() or file.suffix not in _TEST_TYPES:
                continue
            relative = file.relative_to(root).as_posix()
            if not any(isinstance(p, str) and fnmatch(relative, p) for p in patterns):
                continue
            source = file.read_text("utf-8")
            for found in _ENDPOINT.finditer(source):
                # An assertion must belong to this invocation; crossing the
                # next request would attribute an unrelated expectation.
                tail = source[found.end():found.end() + 1200]
                next_request = _ENDPOINT.search(tail)
                if next_request:
                    tail = tail[:next_request.start()]
                statuses = list(_STATUS.finditer(tail))
                if not statuses:
                    continue
                method = found.group("method").lower()
                route = found.group("route")
                targets = [methods for pattern, methods in doc["paths"].items()
                           if isinstance(pattern, str)
                           and isinstance(methods, dict)
                           and _route_matches(pattern, route)
                           and isinstance(methods.get(method), dict)]
                if len(targets) != 1:
                    continue
                operation = targets[0][method]
                responses = operation.get("responses", {})
                if not isinstance(responses, dict):
                    raise AdmissionBlocked("TEST_PROTEGIDO_EN_CONFLICTO")
                for assertion in statuses:
                    expected = _HTTP_STATUS.get(assertion.group("name"))
                    if (expected is not None and str(expected) not in responses
                            and "default" not in responses):
                        raise AdmissionBlocked("TEST_PROTEGIDO_EN_CONFLICTO:"
                                               + relative + ":" + method.upper()
                                               + ":" + route + ":" + str(expected))
