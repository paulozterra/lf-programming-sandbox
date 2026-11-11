#!/usr/bin/env python3
"""CP3.4 native per-lot handoff, entirely offline; no Worker model execution.

Two-stage process:
  register: uses the *actual* pinned connector and emits context/native task.
  export: after committing context, invokes export_task_pack.py against the
          task's exact base commit (never fabricates captured model payload).
No GitHub push, merge or approval is performed by this script.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ORCHESTRATOR = Path(__file__).resolve().parent
ROOT = ORCHESTRATOR.parents[1]
WORKER = ROOT / "pilot/worker_v08"
sys.path.insert(0, str(WORKER))

from native_lot_binding import NativeLotBlocked, map_profile, real_write_paths, next_ready
from register_task_context import (
    ContextBlocked, canonical, native_registration_bytes, register,
    write_native_registration,
)
from export_task_pack import export

SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
TASK_ID = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")


def blocked(message: str):
    raise NativeLotBlocked(message)


def git(root: Path, *args: str) -> str:
    try:
        return subprocess.run(["git", "-C", str(root), *args], check=True,
                              capture_output=True, text=True, timeout=30).stdout.strip()
    except (subprocess.CalledProcessError, OSError, subprocess.TimeoutExpired):
        blocked("CP34_GIT_UNAVAILABLE")


def load(folder: Path, name: str) -> dict:
    target = folder / name
    if target.is_symlink() or not target.is_file():
        blocked("CP34_INPUT_MISSING:" + name)
    try:
        return json.loads(target.read_text("utf-8"))
    except (UnicodeError, ValueError):
        blocked("CP34_INPUT_INVALID:" + name)


def choose(root: Path, request: str, lot_id: str, completed: set[str]):
    folder = root / "pilot/runs" / request
    if folder.is_symlink() or not folder.is_dir():
        blocked("CP34_RUN_INVALID")
    state, lots = load(folder, "state.json"), load(folder, "lots.json")
    if state.get("stage") != "LOTS_PLANNED":
        blocked("CP34_LOTS_NOT_PLANNED")
    if state.get("lots_sha256") != hashlib.sha256(canonical(lots)).hexdigest():
        blocked("CP34_LOTS_SHA_DRIFT")
    candidates = {lot["id"]: lot for lot in next_ready(lots, completed)}
    if lot_id not in candidates:
        blocked("CP34_DEPENDENCY_NOT_VERIFIED")
    lot = candidates[lot_id]
    return folder, lot, map_profile(lot["profile_code"], lot["area"]), real_write_paths(
        root, lot["area"], lot["write_paths"])


def verify_holdout(root: Path, name: str, config: dict) -> tuple[str, str]:
    sha = config.get("holdout_sha256")
    ref = config.get("holdout_ref")
    if not isinstance(sha, str) or not SHA64.fullmatch(sha):
        blocked("CP34_HOLDOUT_SHA_REQUIRED")
    expected = f"pilot/holdouts/{name}.oracle.json.age"
    if ref != expected:
        blocked("CP34_HOLDOUT_REF_INVALID")
    path = root / ref
    if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
        blocked("CP34_HOLDOUT_CIPHERTEXT_MISSING")
    # Never inspect or decrypt the holdout or infer its plaintext checksum.
    return sha, ref


def common(root: Path, folder: Path, lot: dict, mapped: dict,
           paths: list[str], task_name: str, template: dict):
    if not TASK_ID.fullmatch(task_name):
        blocked("CP34_TASK_ID_INVALID")
    if not isinstance(template, dict) or "task_spec" not in template:
        blocked("CP34_TEMPLATE_INVALID")
    spec = template["task_spec"]
    if not isinstance(spec, dict) or spec.get("max_attempts") != 1:
        blocked("CP34_TEMPLATE_INVALID")
    if sorted(spec.get("write_path_patterns", [])) != paths:
        blocked("CP34_SCOPE_MISMATCH")
    head = git(root, "rev-parse", "HEAD")
    if not SHA40.fullmatch(head) or spec.get("base_head_sha") != head:
        blocked("CP34_BASE_NOT_PINNED_TO_HEAD")
    if git(root, "status", "--porcelain"):
        blocked("CP34_WORKTREE_NOT_CLEAN")
    if spec.get("schema_version") != 1:
        blocked("CP34_TASK_SCHEMA_INVALID")
    return spec, head


def register_lot(root: Path, folder: Path, lot: dict, mapped: dict,
                 paths: list[str], task_name: str, template: dict,
                 holdout: dict) -> dict:
    spec, base = common(root, folder, lot, mapped, paths, task_name, template)
    sha, ref = verify_holdout(root, task_name, holdout)
    output, artifacts = register(
        template, project=holdout.get("project_ref", "lf_java"),
        area=lot["area"], lot_paths=paths, task_name=task_name,
        budget=spec.get("max_context_bytes", 240000),
        root=root, persist=False)
    enriched = output["task_spec"]
    native_registration_bytes(enriched, sha, ref, task_name)
    native_file = WORKER / "native_tasks" / (task_name + ".json")
    if native_file.exists() or native_file.is_symlink():
        blocked("CP34_TASK_ALREADY_REGISTERED")
    for rel, raw in artifacts.items():
        target = root / rel
        if target.is_symlink() or (target.exists() and target.read_bytes() != raw):
            blocked("CP34_CONTEXT_CONFLICT")
    for rel, raw in artifacts.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    write_native_registration(root, task_name, native_file, enriched, sha, ref)
    return {"status": "CONTEXT_CREATED_NOT_COMMITTED", "task_name": task_name,
            "lot_id": lot["id"], "base_head_sha": base,
            "profile": mapped, "write_paths": paths,
            "context_paths": sorted(artifacts),
            "native_task": native_file.relative_to(root).as_posix(),
            "production_authority": False}


def export_lot(root: Path, folder: Path, lot: dict, mapped: dict,
               paths: list[str], task_name: str, template: dict, holdout: dict) -> dict:
    sha, ref = verify_holdout(root, task_name, holdout)
    record = load(WORKER / "native_tasks", task_name + ".json")
    spec = record.get("task_spec")
    if (record.get("holdout_sha256") != sha or record.get("holdout_ref") != ref
            or not isinstance(spec, dict)):
        blocked("CP34_NATIVE_REGISTRATION_DRIFT")
    if sorted(spec.get("write_path_patterns", [])) != paths:
        blocked("CP34_SCOPE_MISMATCH")
    base = spec.get("base_head_sha")
    if not isinstance(base, str) or not SHA40.fullmatch(base):
        blocked("CP34_BASE_INVALID")
    # The native Worker reads the base commit, not the present checkout. The
    # three generated files MUST be in that base before export.
    for name in ("profile.md", "skills.md", "receipt.json"):
        rel = f".lf/worker-context/{task_name}/{name}"
        git(root, "cat-file", "-e", f"{base}:{rel}")
    if git(root, "status", "--porcelain"):
        blocked("CP34_WORKTREE_NOT_CLEAN")
    pack_dir = folder / "proposal_requests"
    pack_dir.mkdir(exist_ok=True)
    pack_path = pack_dir / (task_name + ".task-pack.json")
    if pack_path.exists() or pack_path.is_symlink():
        blocked("CP34_PACK_EXISTS")
    pack_hash = export(root, WORKER / "native_tasks" / (task_name + ".json"), pack_path)
    request = {"schema_version": "CP34_NATIVE_PROPOSAL_REQUEST_V1",
               "status": "PROPOSAL_REQUEST_ONLY",
               "task_name": task_name, "lot_id": lot["id"],
               "branch": "lf/native-proposal/" + task_name,
               "base_head_sha": base, "task_spec_path": "pilot/worker_v08/native_tasks/" + task_name + ".json",
               "task_pack_path": pack_path.relative_to(root).as_posix(),
               "task_pack_sha256": pack_hash,
               "profile": mapped,
               "production_authority": False, "model_invoked": False,
               "merge_authorized": False}
    target = pack_dir / (task_name + ".proposal-request.json")
    if target.exists() or target.is_symlink():
        blocked("CP34_REQUEST_EXISTS")
    target.write_bytes(canonical(request))
    return request


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--request-id", required=True)
    ap.add_argument("--lot-id", required=True)
    ap.add_argument("--task-name", required=True)
    ap.add_argument("--template", type=Path, required=True)
    ap.add_argument("--holdout-metadata", type=Path, required=True)
    ap.add_argument("--verified-predecessor", action="append", default=[])
    ap.add_argument("--phase", choices=("register", "export"), required=True)
    args = ap.parse_args()
    try:
        folder, lot, mapped, paths = choose(
            args.root, args.request_id, args.lot_id, set(args.verified_predecessor))
        template = json.loads(args.template.read_text("utf-8"))
        metadata = json.loads(args.holdout_metadata.read_text("utf-8"))
        if args.phase == "register":
            result = register_lot(args.root, folder, lot, mapped, paths,
                                  args.task_name, template, metadata)
        else:
            result = export_lot(args.root, folder, lot, mapped, paths,
                                args.task_name, template, metadata)
    except (NativeLotBlocked, ContextBlocked, OSError, ValueError, KeyError) as exc:
        print("CP34_BLOCKED:" + str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
