#!/usr/bin/env python3
"""CP3.4 native per-lot handoff, entirely offline; no Worker model execution.

Two-stage process:
  register: uses the *actual* pinned connector and emits context/native task.
  export: after committing context, invokes export_task_pack.py against the
          task's exact base commit (never fabricates captured model payload).
No GitHub push, merge or approval is performed by this script.
"""
from __future__ import annotations
# Direct-script entrypoint: resolve the trusted repository root from this file,
# not from the caller's working directory or PYTHONPATH.
import sys as _project_sys
from pathlib import Path as _project_Path
_project_sys.path.insert(0, str(_project_Path(__file__).resolve().parents[2]))
from pilot.config.project_config import storage_path, storage

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

sys.path.insert(0, str(ORCHESTRATOR))
from t4_admission import examinable_requirements
from native_lot_binding import NativeLotBlocked, map_profile, real_write_paths, next_ready
from worker_template_contract import validate_template_worker
from register_task_context import (
    ContextBlocked, canonical, native_registration_bytes, register,
    write_native_registration,
)
from export_task_pack import export
from programming_agent_runner.hashutil import source_snapshot_sha256

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


def verify_handoffs(root: Path, lots: dict, proofs: list[dict]) -> set[str]:
    """A dependent lot never unlocks based on caller-supplied IDs alone.

    CP3.4 validates only explicit, existing merge evidence. The later CP3.6
    stage remains responsible for automatically discovering those receipts.
    """
    completed = set()
    by_id = {item["id"]: item for item in lots.get("lots", [])}
    if not isinstance(proofs, list):
        blocked("CP34_HANDOFF_PROOF_INVALID")
    for proof in proofs:
        if not isinstance(proof, dict):
            blocked("CP34_HANDOFF_PROOF_INVALID")
        lot_id = proof.get("lot_id")
        sha = proof.get("merge_sha")
        files = proof.get("expected_files")
        if (lot_id not in by_id or lot_id in completed or
                not isinstance(sha, str) or not SHA40.fullmatch(sha) or
                not isinstance(files, list) or
                not files or not all(isinstance(f, str) for f in files)
                or not set(files) <= set(by_id[lot_id]["write_paths"])):
            blocked("CP34_HANDOFF_PROOF_INVALID")
        # Prove SHA is on current HEAD history (caller should work on main
        # containing the predecessor merge), not just any reachable object.
        git(root, "merge-base", "--is-ancestor", sha, "HEAD")
        for path in files:
            git(root, "cat-file", "-e", f"{sha}:{path}")
        completed.add(lot_id)
    return completed


def choose(root: Path, request: str, lot_id: str, proofs: list[dict]):
    folder = storage_path("requests_root", root=root) / request
    if folder.is_symlink() or not folder.is_dir():
        blocked("CP34_RUN_INVALID")
    state, lots = load(folder, "state.json"), load(folder, "lots.json")
    if state.get("stage") != "LOTS_PLANNED":
        blocked("CP34_LOTS_NOT_PLANNED")
    if state.get("lots_sha256") != hashlib.sha256(canonical(lots)).hexdigest():
        blocked("CP34_LOTS_SHA_DRIFT")
    completed = verify_handoffs(root, lots, proofs)
    candidates = {lot["id"]: lot for lot in next_ready(lots, completed)}
    if lot_id not in candidates:
        blocked("CP34_DEPENDENCY_NOT_VERIFIED")
    lot = candidates[lot_id]
    return folder, lot, map_profile(lot["profile_code"], lot["area"]), real_write_paths(
        root, lot["area"], lot["write_paths"], lot=lot)


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


def _lot_ekb_context(area: str, artifacts: dict[str, bytes], task_name: str,
                     paths: list[str]) -> tuple[bytes | None, str]:
    try:
        receipt = json.loads(artifacts[f".lf/worker-context/{task_name}/receipt.json"])
        skills = [s.get("code") for s in receipt.get("skills", []) if isinstance(s, dict)]
    except (KeyError, ValueError, AttributeError):
        skills = []
    ekb_dir = Path(__file__).resolve().parents[1] / "ekb"
    if str(ekb_dir) not in sys.path:
        sys.path.insert(0, str(ekb_dir))
    try:
        from route_ekb import context_for_lot
    except ImportError:
        return None, "EKB_CONTEXT_SKIPPED:CLIENT_MISSING"
    return context_for_lot(area, skills, paths)


def register_lot(root: Path, folder: Path, lot: dict, mapped: dict,
                 paths: list[str], task_name: str, template: dict,
                 holdout: dict, *, template_path: str | None = None) -> dict:
    spec, base = common(root, folder, lot, mapped, paths, task_name, template)
    sha, ref = verify_holdout(root, task_name, holdout)
    output, artifacts = register(
        template, project=holdout.get("project_ref", "lf_java"),
        area=lot["area"], lot_paths=paths, task_name=task_name,
        budget=spec.get("max_context_bytes", 240000),
        root=root, persist=False,
        requirement_ids=examinable_requirements(lot))
    # T56: consult the EKB for this lot (area, its skills, its paths). Only
    # a trusted step with the read secret adds ekb.md; it never blocks.
    ekb, ekb_status = _lot_ekb_context(lot["area"], artifacts, task_name, paths)
    print(json.dumps({"route_ekb": ekb_status, "task_name": task_name}), file=sys.stderr)
    if ekb is not None:
        output, artifacts = register(
            template, project=holdout.get("project_ref", "lf_java"),
            area=lot["area"], lot_paths=paths, task_name=task_name,
            budget=spec.get("max_context_bytes", 240000),
            root=root, persist=False,
            requirement_ids=examinable_requirements(lot), ekb_markdown=ekb)
    enriched = output["task_spec"]
    validate_template_worker({"task_spec": enriched}, lot["area"])
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
    stamp_path = None
    stamp_sha = None
    if template_path is not None:
        candidate = root / template_path
        if (candidate.is_symlink() or not candidate.is_file()
                or not candidate.resolve().is_relative_to((storage_path("requests_root", root=root)).resolve())):
            blocked("CP34_TEMPLATE_PROVENANCE_INVALID")
        origin = json.loads(candidate.read_text("utf-8"))
        source_spec = origin.get("task_spec") if isinstance(origin, dict) else None
        if not isinstance(source_spec, dict):
            blocked("CP34_TEMPLATE_PROVENANCE_INVALID")
        stamp_path = template_path
        stamp_sha = hashlib.sha256(canonical(source_spec)).hexdigest()
    write_native_registration(root, task_name, native_file, enriched, sha, ref,
                              stamp_path, stamp_sha)
    return {"status": "CONTEXT_CREATED_NOT_COMMITTED", "task_name": task_name,
            "lot_id": lot["id"], "base_head_sha": base,
            "profile": mapped, "write_paths": paths,
            "context_paths": sorted(artifacts),
            "native_task": native_file.relative_to(root).as_posix(),
            "production_authority": False}


def seal_lot(root: Path, folder: Path, lot: dict, mapped: dict,
             paths: list[str], task_name: str, template: dict, holdout: dict) -> dict:
    """After committing generated context, pin the native task to that commit.

    This deliberately precedes any export. The seal itself must be committed
    before export so the Worker sees exactly the intended task and context.
    """
    sha, ref = verify_holdout(root, task_name, holdout)
    task_file = WORKER / "native_tasks" / (task_name + ".json")
    record = load(WORKER / "native_tasks", task_name + ".json")
    spec = record.get("task_spec")
    if (not isinstance(spec, dict) or record.get("holdout_sha256") != sha
            or record.get("holdout_ref") != ref
            or sorted(spec.get("write_path_patterns", [])) != paths):
        blocked("CP34_NATIVE_REGISTRATION_DRIFT")
    if git(root, "status", "--porcelain"):
        blocked("CP34_WORKTREE_NOT_CLEAN")
    head = git(root, "rev-parse", "HEAD")
    old = spec.get("base_head_sha")
    if old == head or not SHA40.fullmatch(old or ""):
        blocked("CP34_SEAL_BASE_INVALID")
    if git(root, "merge-base", "--is-ancestor", old, head):
        # Success of merge-base has empty stdout. A failing command is
        # handled by git() and therefore fails closed.
        pass
    for name in ("profile.md", "skills.md", "receipt.json"):
        git(root, "cat-file", "-e", f"{head}:.lf/worker-context/{task_name}/{name}")
    sealed = dict(spec, base_head_sha=head,
                  source_snapshot_sha256=source_snapshot_sha256(root))
    # Validate the sealed input against the identical Worker parser used in
    # native_run; registration-time SHA mutations cannot bypass T16.
    validate_template_worker({"task_spec": sealed}, lot["area"])
    payload = native_registration_bytes(sealed, sha, ref, task_name,
                                        record.get("template_path"),
                                        record.get("template_sha256"))
    task_file.write_bytes(payload)
    return {"status": "SEALED_NEEDS_COMMIT", "base_head_sha": head,
            "native_task": task_file.relative_to(root).as_posix(),
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
    # export_task_pack consumes the raw WorkerTaskSpec, not its wrapper.
    # Temporary specs never enter the git repository or the proposal pack.
    import tempfile
    with tempfile.TemporaryDirectory(prefix="cp34-source-") as tmp:
        source = Path(tmp) / "source"
        # The Worker hashes the base source tree. Never export from the control
        # checkout containing the newer sealed registration commit.
        git(root, "worktree", "add", "--detach", str(source), base)
        try:
            raw_spec = Path(tmp) / "task.json"
            raw_spec.write_bytes(canonical(spec))
            try:
                pack_hash = export(source, raw_spec, pack_path)
            except RuntimeError as exc:
                # The vendor capture reports only a bounded machine code;
                # CP3.5/CP3.6 must not bury this behind a generic traceback.
                message = str(exc)
                match = re.fullmatch(
                    r"NATIVE_CAPTURE_FAILED_OR_PREFLIGHT_BLOCKED:([A-Z][A-Z0-9_]{0,79})",
                    message)
                blocked("CP34_EXPORT_" + match.group(1)
                        if match else "CP34_EXPORT_FAILED")
        finally:
            git(root, "worktree", "remove", "--force", str(source))
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
    from native_submission_contract import enrich_request
    target.write_bytes(canonical(enrich_request(request, spec)))
    return request


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--request-id", required=True)
    ap.add_argument("--lot-id", required=True)
    ap.add_argument("--task-name", required=True)
    ap.add_argument("--template", type=Path, required=True)
    ap.add_argument("--holdout-metadata", type=Path, required=True)
    ap.add_argument("--handoff-proof", type=Path, action="append", default=[],
                    help="One JSON proof per merged predecessor (lot_id, merge_sha, expected_files)")
    ap.add_argument("--phase", choices=("register", "seal", "export"), required=True)
    args = ap.parse_args()
    try:
        proofs = [json.loads(path.read_text("utf-8")) for path in args.handoff_proof]
        folder, lot, mapped, paths = choose(
            args.root, args.request_id, args.lot_id, proofs)
        template = json.loads(args.template.read_text("utf-8"))
        metadata = json.loads(args.holdout_metadata.read_text("utf-8"))
        if args.phase == "register":
            result = register_lot(args.root, folder, lot, mapped, paths,
                                  args.task_name, template, metadata)
        elif args.phase == "seal":
            result = seal_lot(args.root, folder, lot, mapped, paths,
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
