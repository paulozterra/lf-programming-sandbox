#!/usr/bin/env python3
"""2B candidate-only pinned LF profile + stack context registration.

No model, Supabase, network, vendor modification or production profile activation.
The caller commits generated context into the task's base tree before dispatch.
"""
from __future__ import annotations

import argparse
import copy
import glob
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
from derive_context import derive, ContextBlocked as DeriveBlocked
from lot_preflight import check_task, LotBlocked

ROOT = Path(__file__).resolve().parents[2]
PINROOT = ROOT / "pilot/lf_profiles_pinned"
PINFILE = PINROOT / "SOURCE_PIN.json"
LF_SHA = "6c3092a88da95a6be5649448c52dd9a920325317"
SHA64 = re.compile(r"^[0-9a-f]{64}$")
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")
NATIVE_ID = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
SHA40 = re.compile(r"^[0-9a-f]{40}$")
PROFILE = {"BACKEND": "prog_backend_exp", "FRONTEND": "prog_frontend_exp",
           "DATA": "prog_data_exp"}
PROFILE_CODE = {"BACKEND": "PERFIL-PROG-BACKEND-EXP",
                "FRONTEND": "PERFIL-PROG-FRONTEND-EXP",
                "DATA": "PERFIL-PROG-DATA-EXP"}
FORMAT_COMMAND = {
    "name": "std-be-05-spotless-check",
    "argv": ["mvn", "-B", "-q", "-f", "apps/time-service/pom.xml", "spotless:check"],
    "timeout_seconds": 600,
    "max_output_bytes": 16000,
}


class ContextBlocked(ValueError):
    pass


def block(reason: str) -> None:
    raise ContextBlocked("REGISTER_CONTEXT_BLOCK:" + reason)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(obj: object) -> bytes:
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")


def safe_rel(value: str) -> str:
    if (not isinstance(value, str) or not value or "\\" in value or
            value.startswith("/") or "\x00" in value or
            any(p in (".", "..") for p in PurePosixPath(value).parts)):
        block("UNSAFE_PATH")
    return value


def read_pins(root: Path = PINROOT) -> tuple[dict, dict[str, bytes]]:
    manifest = json.loads((root / "SOURCE_PIN.json").read_text("utf-8"))
    if (manifest.get("schema_version") != "LF_PROFILE_SOURCE_PIN_V1" or
        manifest.get("source_commit_sha") != LF_SHA or
        manifest.get("source_repository") != "cristhianlujan/claude-persona-lf-patch" or
        manifest.get("status") != "CANDIDATE_SANDBOX_ONLY" or
        manifest.get("production_authority") is not False):
        block("SOURCE_IDENTITY")
    entries = manifest.get("files")
    if not isinstance(entries, dict) or not entries:
        block("SOURCE_MANIFEST_EMPTY")
    present = {p.relative_to(root).as_posix() for p in root.rglob("*")
               if p.is_file() and p.name != "SOURCE_PIN.json"}
    if present != set(entries):
        block("SOURCE_INVENTORY_DRIFT")
    files = {}
    for rel, meta in sorted(entries.items()):
        safe_rel(rel)
        path = root / rel
        if path.is_symlink() or not path.is_file():
            block("SOURCE_SYMLINK_OR_MISSING")
        raw = path.read_bytes()
        if (not isinstance(meta, dict) or len(meta.get("sha256", "")) != 64 or
            not SHA64.fullmatch(meta["sha256"]) or
            digest(raw) != meta["sha256"] or len(raw) != meta.get("bytes")):
            block("SOURCE_PIN_MISMATCH:" + rel)
        git = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        if git != meta.get("git_blob_sha1"):
            block("SOURCE_GIT_BLOB_DRIFT:" + rel)
        files[rel] = raw
    required = {"prog_backend_exp/SKILL.md",
                "prog_backend_exp/contracts/main_contract.md",
                "prog_backend_exp/contracts/runtime_binding.json",
                "prog_frontend_exp/contracts/runtime_binding.json",
                "prog_data_exp/contracts/runtime_binding.json",
                "stack_skills_exp/pg00_normative_catalog_snapshot.json",
                "stack_skills_exp/skill_catalog_exp.json",
                "stack_skills_exp/project_stack_binding_fixtures.json"}
    if not required.issubset(files):
        block("SOURCE_ESSENTIAL_MISSING")
    return manifest, files


def classify_path(value: str) -> str:
    """Never infer from role name alone: only canonical, independently scoped paths."""
    safe_rel(value)
    if (value.startswith("apps/time-service/src/main/java/") or
        value.startswith("backend/src/main/java/") or
        value.startswith("backend/")):
        return "BACKEND"
    if value.startswith(("frontend/", "apps/web/")):
        return "FRONTEND"
    if value.startswith(("db/", "supabase/migrations/", "standards/kit-base/")):
        return "DATA"
    block("UNCLASSIFIED_LOT_PATH:" + value)


def select_area(paths: list[str], declared: str) -> str:
    if not paths or not isinstance(declared, str):
        block("LOT_AREA_REQUIRED")
    areas = {classify_path(p) for p in paths}
    if len(areas) != 1:
        block("LOT_MULTI_AREA")
    actual = next(iter(areas))
    if actual != declared:
        block("LOT_AREA_MISMATCH")
    if actual not in PROFILE:
        block("PROFILE_NOT_AVAILABLE:" + actual)
    return actual


def source_text(files: dict[str, bytes], name: str) -> str:
    try:
        return files[name].decode("utf-8")
    except (KeyError, UnicodeDecodeError):
        block("SOURCE_TEXT_UNAVAILABLE:" + name)


def build_material(files: dict[str, bytes], project: str, area: str) -> tuple[bytes, bytes, list[dict], str]:
    slug = PROFILE[area]
    binding = json.loads(source_text(files, slug + "/contracts/runtime_binding.json"))
    if (binding.get("area") != area or
        binding.get("profile_code") != PROFILE_CODE[area] or
        binding.get("runtime_enabled") is not False or
        binding.get("production_authority") is not False):
        block("PROFILE_BINDING_INVALID")
    profile_parts = [
        "# LF programmer profile / CANDIDATE_SANDBOX_ONLY",
        "Source commit: " + LF_SHA,
    ]
    for name in ("SKILL.md", "contracts/main_contract.md",
                 "contracts/missing_input_policy.md",
                 "checklists/preflight_checklist.md",
                 "checklists/priority_checklist.md"):
        path = slug + "/" + name
        profile_parts.append("\n## " + path + "\n" + source_text(files, path))
    profile_bytes = ("\n".join(profile_parts) + "\n").encode("utf-8")

    stackroot = "stack_skills_exp/"
    rows = json.loads(source_text(files, stackroot + "project_stack_binding_fixtures.json"))["rows"]
    catalog = json.loads(source_text(files, stackroot + "skill_catalog_exp.json"))["skills"]
    bindings = [r for r in rows if r.get("project_ref") == project and r.get("area") == area]
    if not bindings and area != "FRONTEND":
        block("STACK_NOT_BOUND")
    priorities = [r.get("priority") for r in bindings]
    if any(type(p) is not int or p < 1 for p in priorities) or len(set(priorities)) != len(priorities):
        block("STACK_PRIORITY_INVALID")
    bindings = sorted(bindings, key=lambda r: (r["priority"], r["skill_code"]))
    standards = json.loads(source_text(files, stackroot + "pg00_normative_catalog_snapshot.json"))
    source_manifest = json.loads(source_text(files, stackroot + "pg00_catalog_sources_exp.json"))
    if digest(files[stackroot + "pg00_normative_catalog_snapshot.json"]) != source_manifest.get("source_sha256"):
        block("PG00_NORMATIVE_SHA_DRIFT")
    if standards.get("status") != "BORRADOR_EN_REPO_DE_CALIFICACION":
        block("PG00_STATUS_CHANGED")
    by_code = {(r["skill_code"], r["version"]): r for r in catalog}
    skill_parts = ["# LF pinned stack skills / CANDIDATE_SANDBOX_ONLY",
                   "Standards source: " + source_manifest["source_ref"],
                   "Catalog SHA-256: " + source_manifest["source_sha256"]]
    selected = []
    if area == "FRONTEND":
        # The LF fixture is immutable and historically bound to Angular.
        # Only this sandbox explicitly binds FRONTEND to pinned Next.js.
        nextpin_path = ROOT / "pilot/nextjs_source_pin.json"
        if nextpin_path.is_symlink() or not nextpin_path.is_file():
            block("NEXTJS_PIN_MISSING")
        nextpin = json.loads(nextpin_path.read_text("utf-8"))
        if (nextpin.get("schema_version") != "LF_SANDBOX_NEXTJS_PIN_V1"
                or nextpin.get("source_repository") != "paulozterra/lf-programming-sandbox"
                or nextpin.get("skill_path") != "standards/skills/nextjs/SKILL.md"
                or nextpin.get("manifest_path") != "standards/skills/nextjs/skill.json"
                or nextpin.get("skill_id") != "nextjs"
                or nextpin.get("area") != "FRONTEND"
                or nextpin.get("production_authority") is not False):
            block("NEXTJS_PIN_INVALID")
        nextskill = ROOT / nextpin["skill_path"]
        nextmanifest = ROOT / nextpin["manifest_path"]
        if (nextskill.is_symlink() or nextmanifest.is_symlink()
                or not nextskill.is_file() or not nextmanifest.is_file()
                or digest(nextskill.read_bytes()) != nextpin.get("skill_sha256")
                or digest(nextmanifest.read_bytes()) != nextpin.get("manifest_sha256")):
            block("NEXTJS_PIN_SHA_DRIFT")
        metadata = json.loads(nextmanifest.read_text("utf-8"))
        if (metadata.get("skill_id") != nextpin["skill_id"]
                or metadata.get("skill_version") != nextpin.get("skill_version")
                or metadata.get("scope") != "L2_STACK_ONLY"
                or "STD-FE" not in metadata.get("domains", [])):
            block("NEXTJS_METADATA_INVALID")
        official = [r for r in standards["rules"] if r.get("domain") == "STD-FE"]
        if len(official) < 3:
            block("STD_RULES_UNAVAILABLE")
        selected.append({"code": "NEXTJS", "version": metadata["skill_version"],
                         "priority": 1, "sha256": nextpin["skill_sha256"],
                         "rules_sha256": nextpin["manifest_sha256"],
                         "standard_family": "STD-FE"})
        skill_parts.extend(["\n## NEXTJS@" + metadata["skill_version"] + " priority 1",
                            nextskill.read_text("utf-8"),
                            "\n### Literal PG00 STD-FE rules"])
        skill_parts.extend("- " + rule["id"] + " [" + rule["status"] + "]: " + rule["rule"]
                           for rule in official)
        bindings = []
    for row in bindings:
        code, version = row["skill_code"], row["skill_version"]
        entry = by_code.get((code, version))
        if not entry or entry["area"] != area:
            block("STACK_VERSION_OR_AREA_MISMATCH")
        path = stackroot + entry["path"]
        rules_path = stackroot + entry["rules_path"]
        rules = json.loads(source_text(files, rules_path))
        if (rules.get("skill_code") != code or rules.get("version") != version or
            rules.get("standard_family") != entry["standard_family"]):
            block("SKILL_RULES_METADATA_DRIFT")
        official = [r for r in standards["rules"] if r.get("domain") == entry["standard_family"]]
        if len(official) < 3:
            block("STD_RULES_UNAVAILABLE")
        selected.append({"code": code, "version": version, "priority": row["priority"],
                         "sha256": digest(files[path]), "rules_sha256": digest(files[rules_path]),
                         "standard_family": entry["standard_family"]})
        skill_source = source_text(files, path)
        if area == "BACKEND":
            # Deduplicate STD-BE-05 from pinned Spring Boot prose without
            # modifying any pinned source bytes; PG00 emits the canonical rule.
            skill_source = "\n".join(line for line in skill_source.split("\n")
                                      if not line.startswith("- **STD-BE-05:"))
        skill_parts.extend(["\n## " + code + "@" + version + " priority " + str(row["priority"]),
                            skill_source,
                            "\n### Source-bound expert rules\n" + source_text(files, rules_path),
                            "\n### Literal PG00 " + entry["standard_family"] + " rules"])
        skill_parts.extend("- " + r["id"] + " [" + r["status"] + "]: " + r["rule"]
                           for r in official if r["id"] != "STD-BE-05" or
                           not any("STD-BE-05" in part for part in skill_parts))
    skills_bytes = ("\n".join(skill_parts) + "\n").encode("utf-8")
    return profile_bytes, skills_bytes, selected, source_manifest["source_sha256"]


def expanded_context_size(root: Path, patterns: list[str], excluded: set[str]) -> int:
    paths = set()
    for pattern in patterns:
        safe_rel(pattern)
        for match in glob.glob(str(root / pattern), recursive=True):
            file = Path(match)
            if file.is_file() and not file.is_symlink():
                rel = file.relative_to(root).as_posix()
                if rel not in excluded:
                    paths.add(rel)
    return sum((root / name).stat().st_size for name in paths)


def register(task: dict, *, project: str, area: str, lot_paths: list[str],
             task_name: str, budget: int, root: Path = ROOT,
             pinned: Path = PINROOT, persist: bool = True) -> tuple[dict, dict[str, bytes]]:
    if not ID.fullmatch(task_name):
        block("TASK_ID_UNSAFE")
    if task_name.lower() in {"ex6", "ex7"}:
        block("HISTORICAL_TASK_IMMUTABLE")
    if budget <= 0 or budget > 2_000_000:
        block("CONTEXT_BUDGET_INVALID")
    # Preserve the historical security failure code before generic lot
    # classification/mismatch (generated context is NEVER a write target).
    proposed = task.get("task_spec", task)
    if isinstance(proposed, dict) and any(
            isinstance(p, str) and p.startswith(".lf/worker-context/")
            for p in proposed.get("write_path_patterns", [])):
        block("CONTEXT_WRITE_SCOPE_OVERLAP")
    selected = select_area(lot_paths, area)
    spec_input = task.get("task_spec", task)
    if not isinstance(spec_input, dict):
        block("TASK_SPEC_INVALID")
    if sorted(set(lot_paths)) != sorted(set(spec_input.get("write_path_patterns", []))):
        block("LOT_WRITE_SCOPE_MISMATCH")
    try:
        spec_paths = spec_input.get("spec_paths")
        if spec_paths is None:
            spec_paths = [spec_input["spec_path"]] if spec_input.get("spec_path") else []
            spec_paths += [p for p in spec_input.get("context_path_patterns", [])
                           if isinstance(p, str) and p.endswith((".md", ".txt"))]
        derived = derive(root, lot_paths, sorted(set(spec_paths)))
    except (DeriveBlocked, TypeError, KeyError) as exc:
        block(str(exc))
    # Derive first; then gate the exact effective read scope before publishing.
    if not (root / ".git").exists():
        block("LOT_PREFLIGHT_NO_GIT")
    if task_name.lower() not in {"ex6", "ex7", "ex8"}:
        prepared = copy.deepcopy(task)
        effective = prepared.get("task_spec", prepared)
        effective["context_path_patterns"] = sorted(set(
            effective.get("context_path_patterns", []) + derived["context_paths"]))
        try:
            check_task(root, prepared)
        except LotBlocked as exc:
            block(str(exc))
    manifest, files = read_pins(pinned)
    profile, skills, identities, catalog_sha = build_material(files, project, selected)
    spec = task.get("task_spec") if "task_spec" in task else task
    if not isinstance(spec, dict):
        block("TASK_SPEC_INVALID")
    if spec.get("task_id") in {"LF-WORKER-NATIVE-EX6", "LF-WORKER-NATIVE-EX7"}:
        block("HISTORICAL_TASK_IMMUTABLE")
    output = copy.deepcopy(task)
    dest = output["task_spec"] if "task_spec" in output else output
    paths = [f".lf/worker-context/{task_name}/{x}" for x in ("profile.md", "skills.md", "receipt.json")]
    context = list(dest.get("context_path_patterns", []))
    # Existing task context is retained; derived sources are selected without
    # hand-editing context_path_patterns.
    for selected_path in derived["context_paths"]:
        if selected_path not in context:
            context.append(selected_path)
    protected = list(dest.get("protected_path_patterns", []))
    writes = list(dest.get("write_path_patterns", []))
    if any(any(p == w or w.startswith(".lf/worker-context/") for w in writes) for p in paths):
        block("CONTEXT_WRITE_SCOPE_OVERLAP")
    if any(not isinstance(v, list) for v in (context, protected, writes)):
        block("TASK_SCOPE_SHAPE")
    for p in paths:
        if p not in context:
            context.append(p)
        if p not in protected:
            protected.append(p)
    commands = list(dest.get("acceptance_commands", []))
    if not isinstance(commands, list):
        block("ACCEPTANCE_COMMANDS_INVALID")
    if area == "BACKEND" and any("SPRINGBOOT_EXP" == r["code"] for r in identities):
        if FORMAT_COMMAND not in commands:
            if any(c.get("name") == FORMAT_COMMAND["name"] for c in commands if isinstance(c, dict)):
                block("FORMAT_ACCEPTANCE_NAME_COLLISION")
            commands.append(copy.deepcopy(FORMAT_COMMAND))
    existing = expanded_context_size(root, list(dest.get("context_path_patterns", [])), set(paths))
    receipt = {
        "schema_version": "LF_WORKER_PINNED_CONTEXT_RECEIPT_V1",
        "status": "CANDIDATE_SANDBOX_ONLY",
        "source_repository": manifest["source_repository"],
        "source_commit_sha": LF_SHA,
        "source_pin_sha256": digest((pinned / "SOURCE_PIN.json").read_bytes()),
        "profile": {"code": PROFILE_CODE[area], "sha256": digest(profile),
                    "source_files": {k: v["sha256"] for k, v in manifest["files"].items()
                                     if k.startswith(PROFILE[area] + "/")}},
        "skills": identities,
        "catalog_sha256": catalog_sha,
        "project_ref": project,
        "area": area,
        "task_name": task_name,
        "source_lot_paths": sorted(set(lot_paths)),
        "derived_context_sha256": digest(
            (json.dumps(derived, sort_keys=True, ensure_ascii=False,
                        separators=(",", ":")) + "\n").encode("utf-8")),
        "context_paths": paths,
        "context_sha256": {"profile.md": digest(profile), "skills.md": digest(skills)},
        "production_authority": False,
    }
    receipt_raw = canonical(receipt)
    artifacts = dict(zip(paths, (profile, skills, receipt_raw)))
    cap = min(budget, dest.get("max_context_bytes", budget))
    if existing + sum(map(len, artifacts.values())) > cap:
        block("CONTEXT_BUDGET_EXCEEDED")
    dest["context_path_patterns"] = context
    dest["protected_path_patterns"] = protected
    dest["acceptance_commands"] = commands
    if persist:
        # Fail closed before touching any path; do not silently replace an older receipt.
        for name, raw in artifacts.items():
            path = root / name
            if path.is_symlink() or (path.exists() and path.read_bytes() != raw):
                block("CONTEXT_OUTPUT_CONFLICT:" + name)
        for name, raw in artifacts.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
    return output, artifacts


def native_registration_bytes(task_spec: dict, holdout_sha256: str) -> bytes:
    """Same two-key schema consumed by native_run.load_registration."""
    if not isinstance(holdout_sha256, str) or not SHA64.fullmatch(holdout_sha256):
        block("NATIVE_HOLDOUT_SHA_INVALID")
    if not isinstance(task_spec, dict) or task_spec.get("max_attempts") != 1:
        block("NATIVE_TASK_SPEC_INVALID")
    if not isinstance(task_spec.get("base_head_sha"), str) or not SHA40.fullmatch(task_spec["base_head_sha"]):
        block("NATIVE_BASE_HEAD_INVALID")
    return canonical({"task_spec": task_spec, "holdout_sha256": holdout_sha256})


def native_path(root: Path, task_name: str, native_out: Path) -> Path:
    if not isinstance(task_name, str) or not NATIVE_ID.fullmatch(task_name):
        block("NATIVE_TASK_ID_INVALID")
    if task_name in {"ex6", "ex7", "ex8"}:
        block("HISTORICAL_TASK_IMMUTABLE")
    expected = root / "pilot/worker_v08/native_tasks" / (task_name + ".json")
    if native_out != expected and native_out.resolve() != expected.resolve():
        block("NATIVE_TASK_PATH_INVALID")
    destination = expected
    base = root / "pilot/worker_v08/native_tasks"
    if base.is_symlink() or destination.is_symlink() or not destination.resolve().is_relative_to(base.resolve()):
        block("NATIVE_TASK_PATH_INVALID")
    return destination


def write_native_registration(root: Path, task_name: str, native_out: Path,
                              task_spec: dict, holdout_sha256: str) -> bytes:
    destination = native_path(root, task_name, native_out)
    payload = native_registration_bytes(task_spec, holdout_sha256)
    if destination.exists():
        if not destination.is_file() or destination.read_bytes() != payload:
            block("NATIVE_TASK_EXISTS")
        return payload  # deterministic replay: identical bytes, no rewrite
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation, never overwrite a concurrent registration.
    try:
        with destination.open("xb") as target:
            target.write(payload)
    except FileExistsError:
        block("NATIVE_TASK_EXISTS")
    return payload


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--task-file", type=Path, required=True)
    p.add_argument("--out-task", type=Path)
    p.add_argument("--native-out", type=Path,
                   help="Native task registration at pilot/worker_v08/native_tasks/<t>.json")
    p.add_argument("--holdout-sha256", help="External 64-hex digest, never the oracle body")
    p.add_argument("--task-name", required=True)
    p.add_argument("--project", required=True)
    p.add_argument("--area", required=True, choices=("BACKEND", "FRONTEND", "DATA"))
    p.add_argument("--lot-path", required=True, action="append")
    p.add_argument("--context-budget-bytes", required=True, type=int)
    args = p.parse_args()
    if not args.out_task and not args.native_out:
        block("TASK_OUTPUT_REQUIRED")
    if args.native_out is None and args.holdout_sha256 is not None:
        block("NATIVE_TASK_PATH_INVALID")
    if args.native_out is not None:
        native_path(ROOT, args.task_name, args.native_out)
        native_registration_bytes(
            json.loads(args.task_file.read_text("utf-8")).get("task_spec", {}),
            args.holdout_sha256)
    if args.out_task and args.task_file.resolve() == args.out_task.resolve():
        block("TASK_INPUT_IMMUTABLE")
    # Generated task registrations must not overwrite vendor/, production profiles,
    # historical native_tasks/, or any unrelated repository file.
    if args.out_task:
        permitted = (ROOT / "pilot/worker_v08/registered_tasks").resolve()
        candidate = args.out_task.resolve()
        if not candidate.is_relative_to(permitted) or candidate.suffix != ".json":
            block("TASK_OUTPUT_SCOPE_INVALID")
        if args.out_task.exists() or args.out_task.is_symlink():
            block("TASK_OUTPUT_EXISTS")
    task = json.loads(args.task_file.read_text("utf-8"))
    enriched, _ = register(task, project=args.project, area=args.area,
                           lot_paths=args.lot_path, task_name=args.task_name,
                           budget=args.context_budget_bytes)
    if args.native_out:
        spec = enriched["task_spec"] if "task_spec" in enriched else enriched
        write_native_registration(ROOT, args.task_name, args.native_out, spec,
                                  args.holdout_sha256)
    if args.out_task:
        if args.out_task.exists():
            block("TASK_OUTPUT_EXISTS")
        args.out_task.parent.mkdir(parents=True, exist_ok=True)
        args.out_task.write_bytes(canonical(enriched))
    print("LF_PINNED_WORKER_CONTEXT_REGISTERED " + args.task_name)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ContextBlocked, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
