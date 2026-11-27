#!/usr/bin/env python3
"""T31: the only way the independent examiner prepares a hidden exam.

Runs, in the examiner's private workspace and before anything is published,
the same checks the trusted Worker applies, then writes ciphertext and
metadata that are consistent by construction:

1. build the oracle from a check script, split into Worker-sized argv chunks;
2. load it with the vendored Worker loader (load_hidden_oracle and
   assert_hidden_oracle_external);
3. run it, in a clean copy of git-tracked files (as the Worker does), against
   the reference overlay (must PASS) and each mutant overlay (each must FAIL);
4. encrypt to the repository recipient, decrypt back and compare bytes;
5. write metadata whose holdout_sha256 is the plaintext SHA the Worker checks.

Any failure stops before writing to the repository. Plaintext never enters
the repository; only ciphertext and metadata do.
"""
from __future__ import annotations
# Resolve the trusted repository package for direct script execution.
import sys as _project_sys
from pathlib import Path as _project_Path
_project_sys.path.insert(0, str(_project_Path(__file__).resolve().parents[2]))
from pilot.config.project_config import storage_path, storage
from pilot.orchestrator.examiner_brief import BriefBlocked, require_lot_rules, resolve_fiche_rule

import argparse
import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "vendor/programming-agent/src"))

TASK = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
CHUNK_BYTES = 4000          # Worker limit is 4096 bytes per argument.
MAX_ARGS = 64               # Worker limit on argv length.
EXEC_PREFIX = ["lf-python", "-c", "import sys;exec(''.join(sys.argv[1:]))"]


class ExamBlocked(RuntimeError):
    pass


def chunks(script: str) -> list[str]:
    out, cur = [], ""
    for ch in script:
        if len((cur + ch).encode("utf-8")) > CHUNK_BYTES:
            out.append(cur)
            cur = ""
        cur += ch
    if cur:
        out.append(cur)
    if "".join(out) != script or len(out) + len(EXEC_PREFIX) > MAX_ARGS:
        raise ExamBlocked("EXAM_SCRIPT_TOO_LARGE")
    return out


def build_oracle(script: str, *, name: str, family: str, version: str,
                 timeout: int, max_output: int) -> bytes:
    oracle = {"commands": [{"argv": [*EXEC_PREFIX, *chunks(script)],
                            "max_output_bytes": max_output, "name": name,
                            "timeout_seconds": timeout}],
              "family": family, "schema_version": 1, "version": version}
    return (json.dumps(oracle, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def worker_load(raw: bytes, root: Path) -> None:
    from programming_agent_runner.worker_oracle import (
        assert_hidden_oracle_external, load_hidden_oracle)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "holdout.oracle.json"
        path.write_bytes(raw)
        try:
            oracle = load_hidden_oracle(path, hashlib.sha256(raw).hexdigest())
            assert_hidden_oracle_external(root, oracle)
        except Exception as exc:  # report the Worker's own code
            raise ExamBlocked("EXAM_WORKER_LOADER_REJECTED:" + str(exc).split(":")[0]) from None


def overlay(base: Path, files: Path, dest: Path) -> None:
    """dest = copy of base worktree with files/<repo path> laid over it."""
    for src in sorted(p for p in files.rglob("*") if p.is_file()):
        rel = src.relative_to(files)
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, target)


def command_env() -> dict:
    """Like the Worker bridge: fictitious SBX_FIXTURE_* credentials by env."""
    from pilot.worker_v08.fixture_credentials import fixture_environment
    return {**os.environ, **fixture_environment()}


def run_oracle(raw: bytes, workdir: Path, python: str) -> bool:
    for cmd in json.loads(raw)["commands"]:
        argv = list(cmd["argv"])
        if argv[0] == "lf-python":
            argv[0] = python
        try:
            result = subprocess.run(argv, cwd=workdir, capture_output=True, text=True,
                                    timeout=cmd["timeout_seconds"], env=command_env())
        except subprocess.TimeoutExpired:
            return False
        if result.returncode != 0:
            return False
    return True


def clean_copy(worktree: Path, dest: Path) -> Path:
    """T31.1: like the Worker, run the oracle on git-tracked files only
    (no node_modules, build caches or other local state)."""
    listed = subprocess.run(["git", "ls-files", "-z"], cwd=worktree, check=True,
                            capture_output=True).stdout.split(b"\0")
    for raw in listed:
        if not raw:
            continue
        rel = raw.decode("utf-8")
        src = worktree / rel
        if src.is_symlink() or not src.is_file():
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, target)
    return dest


def worker_order_copy(candidate: Path, dest: Path) -> Path:
    """Copy every file of `candidate` in sorted relative-path order, like
    worker_workspace.copy_candidate_for_commands."""
    files = sorted(p.relative_to(candidate).as_posix() for p in candidate.rglob("*")
                   if p.is_file() and not p.is_symlink())
    for rel in files:
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(candidate / rel, target)
    return dest


def exercise(raw: bytes, worktree: Path, reference: Path, mutants: list[Path],
             python: str) -> dict:
    results = {}
    for label, files in [("reference", reference)] + [(m.name, m) for m in mutants]:
        with tempfile.TemporaryDirectory(prefix="lf-exam-case-") as tmp:
            # T39: same order as the Worker: base + change in a candidate, then
            # the commands workspace copied path by path in sorted order (so
            # e.g. a tracked build output gets a newer mtime than the sources).
            candidate = clean_copy(worktree, Path(tmp) / "candidate")
            overlay(candidate, files, candidate)
            case = worker_order_copy(candidate, Path(tmp) / "commands")
            results[label] = run_oracle(raw, case, python)
    if not results.get("reference"):
        raise ExamBlocked("EXAM_REFERENCE_DOES_NOT_PASS")
    survivors = sorted(k for k, ok in results.items() if k != "reference" and ok)
    if survivors:
        raise ExamBlocked("EXAM_MUTANTS_SURVIVE:" + ",".join(survivors))
    if not mutants:
        raise ExamBlocked("EXAM_WITHOUT_MUTANTS")
    return results


def lot_area(folder: Path, task: str) -> str | None:
    """Area of the task's lot (chain_plan binding -> lots.json)."""
    try:
        plan = json.loads((folder / "chain_plan.json").read_text("utf-8"))
        lot_id = next(b["lot_id"] for b in plan["bindings"] if b["task_name"] == task)
        lots = json.loads((folder / "lots.json").read_text("utf-8"))
        lots = lots["lots"] if isinstance(lots, dict) else lots
        return next(l["area"] for l in lots if l["id"] == lot_id)
    except (OSError, ValueError, KeyError, TypeError, StopIteration):
        return None


def standards_commands(folder: Path, task: str, commands: list) -> list:
    """Visible commands the registration ADDS to the template (STD-BE-05
    Spotless for BACKEND lots), so the preflight runs what T40 will run."""
    if lot_area(folder, task) != "BACKEND":
        return []
    worker_dir = str(Path(__file__).resolve().parents[1] / "worker_v08")
    if worker_dir not in sys.path:
        sys.path.insert(0, worker_dir)  # register_task_context imports its siblings flat
    from pilot.worker_v08.register_task_context import format_command
    extra = format_command()
    return [extra] if extra is not None and extra not in commands else []


def visible_preflight(root: Path, request: str, task: str, worktree: Path,
                      reference: Path, python: str) -> None:
    """Run the lot template's visible acceptance commands on base + reference
    (Worker order) before publishing; fail with the first failing command."""
    folder = storage_path("requests_root", root=root) / request
    try:
        spec = json.loads((folder / "templates" / f"{task}.task.json").read_text("utf-8"))["task_spec"]
        commands = spec["acceptance_commands"]
    except (OSError, ValueError, KeyError, TypeError):
        raise ExamBlocked("EXAM_VISIBLE_COMMANDS_UNRESOLVED") from None
    if not isinstance(commands, list):
        raise ExamBlocked("EXAM_VISIBLE_COMMANDS_UNRESOLVED")
    commands = commands + standards_commands(folder, task, commands)
    with tempfile.TemporaryDirectory(prefix="lf-exam-visible-") as tmp:
        candidate = clean_copy(worktree, Path(tmp) / "candidate")
        overlay(candidate, reference, candidate)
        case = worker_order_copy(candidate, Path(tmp) / "commands")
        for cmd in commands:
            argv = list(cmd.get("argv") or [])
            name = str(cmd.get("name", "?"))
            if not argv:
                raise ExamBlocked("EXAM_VISIBLE_COMMANDS_UNRESOLVED")
            if argv[0] == "lf-python":
                argv[0] = python
            try:
                result = subprocess.run(argv, cwd=case, capture_output=True, text=True,
                                        timeout=int(cmd.get("timeout_seconds", 600)),
                                        env=command_env())
            except (OSError, subprocess.TimeoutExpired):
                raise ExamBlocked("EXAM_REFERENCE_FAILS_VISIBLE:" + name) from None
            if result.returncode != 0:
                raise ExamBlocked("EXAM_REFERENCE_FAILS_VISIBLE:" + name)


FAIL_CODE = re.compile(r"""fail\(\s*f?["']([A-Z][A-Z0-9_]*)""")
TRACE_KINDS = ("rule:", "contract:", "request:", "env:")


def check_trace(script: str, trace: dict, worktree: Path, reference: Path,
                request: str) -> None:
    """T40 capa 3: every failure code of the exam is traced to what the
    constructor was given: a fiche rule, a contract file, the request's own
    decisions, or an environment probe (build/start). Untraced code -> blocked."""
    codes = set(FAIL_CODE.findall(script))
    if not codes:
        raise ExamBlocked("EXAM_TRACE_NO_FAIL_CODES")
    if not isinstance(trace, dict) or set(trace) != codes:
        missing = sorted(codes - set(trace or {}))
        extra = sorted(set(trace or {}) - codes)
        raise ExamBlocked("EXAM_TRACE_MISMATCH:" + ",".join(
            ["missing=" + c for c in missing] + ["unused=" + c for c in extra]))
    for code, target in sorted(trace.items()):
        if not isinstance(target, str) or not target.startswith(TRACE_KINDS):
            raise ExamBlocked("EXAM_TRACE_KIND_INVALID:" + code)
        kind, value = target.split(":", 1)
        value = value.strip()
        if not value:
            raise ExamBlocked("EXAM_TRACE_EMPTY:" + code)
        if kind == "rule":
            state = resolve_fiche_rule(ROOT, request, value)["status"]
            if state != "VALID":
                reason = "UNKNOWN" if state == "MISSING" else state
                raise ExamBlocked("EXAM_TRACE_RULE_" + reason + ":" + code + "=" + value)
        if kind == "contract" and not ((worktree / value).is_file() or (reference / value).is_file()):
            raise ExamBlocked("EXAM_TRACE_CONTRACT_UNKNOWN:" + code + "=" + value)
        if kind == "request" and value.split()[0] != request:
            raise ExamBlocked("EXAM_TRACE_REQUEST_MISMATCH:" + code)


def check_trace_lot(root: Path, request: str, task: str, trace: dict) -> None:
    """T58: a ``rule:`` trace must name a rule the lot itself carries (one of its
    REQ-<code>) or a catalogue standard (STD-*). Citing a fiche rule of another
    lot or screen means the exam demands something this constructor was not
    asked for (req-391: DATA v1 demanded seeds no DATA rule allows)."""
    folder = storage_path("requests_root", root=root) / request
    try:
        spec = json.loads((folder / "templates" / f"{task}.task.json").read_text("utf-8"))["task_spec"]
        lots = json.loads((folder / "lots.json").read_text("utf-8"))["lots"]
    except (OSError, ValueError, KeyError, TypeError):
        raise ExamBlocked("EXAM_TRACE_LOT_UNRESOLVED") from None
    scope = sorted(spec.get("write_path_patterns") or [])
    rows = [lot for lot in lots if isinstance(lot, dict) and sorted(lot.get("write_paths") or []) == scope]
    if len(rows) != 1:
        raise ExamBlocked("EXAM_TRACE_LOT_UNRESOLVED")
    lot = rows[0]
    bound = (lot.get("characterized_requirement_ids") if lot.get("lot_kind") == "CHARACTERIZATION"
             else lot.get("requirement_ids"))
    # Check every lot obligation before any reference build or publication,
    # even when all failure codes use contract/request/env/STD traces.
    try:
        require_lot_rules(root, request, bound)
    except BriefBlocked as exc:
        raise ExamBlocked(str(exc)) from None
    allowed = {r[len("REQ-"):] for r in bound}
    for code, target in sorted(trace.items()):
        kind, _, value = str(target).partition(":")
        value = value.strip()
        if kind == "rule" and not value.startswith("STD-") and value not in allowed:
            raise ExamBlocked("EXAM_TRACE_RULE_NOT_IN_LOT:" + code + "=" + value)


def lint_script(script: str) -> None:
    """Reject untraceable exam failures without running any build."""
    if not FAIL_CODE.findall(script):
        raise ExamBlocked("EXAM_TRACE_NO_FAIL_CODES")
    try:
        syntax = ast.parse(script)
    except SyntaxError:
        raise ExamBlocked("EXAM_LINT_SYNTAX") from None
    if any(isinstance(node, ast.Assert) for node in ast.walk(syntax)):
        raise ExamBlocked("EXAM_LINT_ASSERT")


def lint_timeout(seconds: int) -> None:
    """Read accepted timeout bounds from the pinned Worker validator itself."""
    from programming_agent_runner.worker_spec import TaskSpecError, _acceptance_commands
    try:
        _acceptance_commands([{
            "name": "lint", "argv": ["lf-python", "-c", "pass"],
            "timeout_seconds": seconds, "max_output_bytes": 1024,
        }])
    except TaskSpecError:
        raise ExamBlocked("EXAM_LINT_TIMEOUT") from None


def lint_overlay_scope(root: Path, request: str, task: str,
                       reference: Path, mutants: list[Path]) -> None:
    """An examiner control overlay may only modify its task's declared lot."""
    def reject():
        raise ExamBlocked("EXAM_REFERENCE_OUT_OF_SCOPE")

    try:
        folder = storage_path("requests_root", root=root) / request
        if not folder.is_dir() or folder.is_symlink():
            reject()
        lots_path, plan_path = folder / "lots.json", folder / "chain_plan.json"
        if any(p.is_symlink() or not p.is_file() for p in (lots_path, plan_path)):
            reject()
        lots = json.loads(lots_path.read_text("utf-8"))
        plan = json.loads(plan_path.read_text("utf-8"))
        bindings = [row for row in plan["bindings"]
                    if row.get("task_name") == task]
        if len(bindings) != 1:
            reject()
        lot_rows = [row for row in lots["lots"]
                    if row.get("id") == bindings[0]["lot_id"]]
        if len(lot_rows) != 1:
            reject()
        paths = lot_rows[0]["write_paths"]
        if (not isinstance(paths, list) or not paths
                or any(not isinstance(p, str) or not p
                       or Path(p).is_absolute() or "\\" in p
                       or ".." in Path(p).parts for p in paths)):
            reject()
        allowed = set(paths)
        for folder in [reference, *mutants]:
            if not folder.is_dir() or folder.is_symlink():
                reject()
            for item in folder.rglob("*"):
                if item.is_symlink():
                    reject()
                if item.is_file() and item.relative_to(folder).as_posix() not in allowed:
                    reject()
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        reject()


def reference_patch(worktree: Path, reference: Path) -> str:
    """The reference as a unified diff against the base (git apply-able)."""
    with tempfile.TemporaryDirectory(prefix="lf-exam-ref-") as tmp:
        repo = clean_copy(worktree, Path(tmp) / "repo")
        git = ["git", "-c", "user.name=lf", "-c", "user.email=lf@sandbox.test",
               "-c", "core.autocrlf=false", "-C", str(repo)]
        subprocess.run(git + ["init", "-q"], check=True, capture_output=True)
        subprocess.run(git + ["add", "-A"], check=True, capture_output=True)
        subprocess.run(git + ["commit", "-qm", "base"], check=True, capture_output=True)
        overlay(repo, reference, repo)
        subprocess.run(git + ["add", "-A"], check=True, capture_output=True)
        patch = subprocess.run(git + ["diff", "--cached", "--no-color", "--no-renames"],
                               check=True, capture_output=True, text=True).stdout
    if not patch.strip():
        raise ExamBlocked("EXAM_REFERENCE_EMPTY")
    return patch


def reference_package(task: str, raw: bytes, patch: str) -> bytes:
    return (json.dumps({"schema_version": "LF_EXAM_REFERENCE_V1", "task": task,
                        "holdout_sha256": hashlib.sha256(raw).hexdigest(),
                        "patch": patch}, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def encrypt_roundtrip(raw: bytes, recipient: Path, identity: Path | None, out: Path) -> None:
    subprocess.run(["age", "-R", str(recipient), "-o", str(out)], input=raw, check=True)
    if identity is None:
        # The private key stays in GitHub (PILOT_HOLDOUT_AGE_KEY): the T40
        # rehearsal in the real Worker decrypts and compares the SHA instead.
        return
    back = subprocess.run(["age", "-d", "-i", str(identity), str(out)],
                          capture_output=True, check=True).stdout
    if back != raw:
        out.unlink(missing_ok=True)
        raise ExamBlocked("EXAM_ENCRYPTION_ROUNDTRIP_MISMATCH")


def lifecycle_api(path):
    """Read live authorization via the examiner's authenticated gh session."""
    return json.loads(subprocess.run(["gh", "api", "repos/paulozterra/lf-programming-sandbox/" + path],
                                     check=True, capture_output=True, text=True, timeout=30).stdout)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--task", required=True)
    p.add_argument("--request", required=True)
    p.add_argument("--script", type=Path, required=True)
    p.add_argument("--family", required=True)
    p.add_argument("--version", required=True)
    p.add_argument("--name", default="holdout")
    p.add_argument("--timeout", type=int, default=300)
    p.add_argument("--max-output", type=int, default=8000)
    p.add_argument("--worktree", type=Path, required=True,
                   help="scratch checkout of current main used to run the exam")
    p.add_argument("--reference", type=Path, required=True)
    p.add_argument("--mutants", type=Path, required=True,
                   help="directory with one overlay directory per mutant")
    p.add_argument("--identity", type=Path, default=None,
                   help="optional local round-trip; without it T40 verifies decryption")
    p.add_argument("--derived-from", required=True)
    p.add_argument("--python", default=sys.executable)
    p.add_argument("--project-ref", default="lf_java")
    p.add_argument("--trace", type=Path, required=True,
                   help="T40: JSON {FAIL_CODE: rule:<id>|contract:<path>|request:<slug> ...|env:<why>}")
    p.add_argument("--add-reference", action="store_true",
                   help="T40: exam already published unchanged; only add its reference")
    a = p.parse_args()
    try:
        from pilot.orchestrator.request_lifecycle import require_open, request_for_task, RequestStateError
        def lifecycle_guard():
            if request_for_task(a.task, root=ROOT, registered=False) != a.request:
                raise ExamBlocked("EXAM_REQUEST_UNVERIFIED")
            require_open(a.request, lifecycle_api, root=ROOT)
        if not TASK.fullmatch(a.task):
            raise ExamBlocked("EXAM_TASK_INVALID")
        if a.worktree.resolve() == ROOT.resolve():
            raise ExamBlocked("EXAM_WORKTREE_MUST_BE_SCRATCH")
        lifecycle_guard()
        script = a.script.read_text("utf-8")
        lint_script(script)
        lint_timeout(a.timeout)
        raw = build_oracle(script, name=a.name, family=a.family,
                           version=a.version, timeout=a.timeout, max_output=a.max_output)
        # Load all chunks with the actual vendor oracle validator BEFORE
        # reference/mutant builds or any worktree copy.
        worker_load(raw, ROOT)
        try:
            trace = json.loads(a.trace.read_text("utf-8"))
        except (OSError, ValueError):
            raise ExamBlocked("EXAM_TRACE_UNREADABLE") from None
        check_trace(script, trace, a.worktree, a.reference, a.request)
        check_trace_lot(ROOT, a.request, a.task, trace)
        mutants = sorted(d for d in a.mutants.iterdir() if d.is_dir())
        lint_overlay_scope(ROOT, a.request, a.task, a.reference, mutants)
        # The reference must also pass the lot's VISIBLE commands, exactly as
        # the T40 rehearsal will run them (req-652: a BACKEND reference without
        # contract operations passed its own exam but failed T40).
        visible_preflight(ROOT, a.request, a.task, a.worktree, a.reference, a.python)
        results = exercise(raw, a.worktree, a.reference, mutants, a.python)
        package = reference_package(a.task, raw, reference_patch(a.worktree, a.reference))
        cipher = ROOT / "pilot/holdouts" / f"{a.task}.oracle.json.age"
        ref_cipher = ROOT / "pilot/holdouts" / f"{a.task}.reference.json.age"
        recipient = ROOT / "pilot/holdouts/recipient.txt"
        lifecycle_guard()
        if a.add_reference:
            meta_file = storage_path("requests_root", root=ROOT) / a.request / "claude_meta" / f"{a.task}.json"
            try:
                published = json.loads(meta_file.read_text("utf-8"))["holdout_sha256"]
            except (OSError, ValueError, KeyError):
                raise ExamBlocked("EXAM_NOT_PUBLISHED") from None
            if not cipher.exists() or published != hashlib.sha256(raw).hexdigest():
                raise ExamBlocked("EXAM_CHANGED_USE_NEW_VERSION_PR")
            # The reference is the examiner's control, not the exam: replacing it
            # (e.g. re-based to the registered base) does not change what is graded.
            ref_cipher.unlink(missing_ok=True)
            encrypt_roundtrip(package, recipient, a.identity, ref_cipher)
            print(json.dumps({"status": "EXAM_REFERENCE_READY", "task": a.task,
                              "holdout_sha256": published}))
            return 0
        if cipher.exists() or ref_cipher.exists():
            raise ExamBlocked("EXAM_ALREADY_PUBLISHED_USE_NEW_VERSION_PR")
        encrypt_roundtrip(raw, recipient, a.identity, cipher)
        encrypt_roundtrip(package, recipient, a.identity, ref_cipher)
        meta = storage_path("requests_root", root=ROOT) / a.request / "claude_meta" / f"{a.task}.json"
        meta.parent.mkdir(parents=True, exist_ok=True)
        meta.write_text(json.dumps({
            "holdout_ref": f"pilot/holdouts/{a.task}.oracle.json.age",
            "holdout_sha256": hashlib.sha256(raw).hexdigest(),
            "project_ref": a.project_ref, "written_by": "claude",
            "derived_from": a.derived_from}, indent=2, ensure_ascii=False) + "\n", "utf-8")
    except (ExamBlocked, RequestStateError) as exc:
        print(str(exc))
        return 1
    print(json.dumps({"status": "EXAM_READY_TO_PUBLISH", "task": a.task,
                      "mutants_killed": len(results) - 1,
                      "holdout_sha256": hashlib.sha256(raw).hexdigest()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
