#!/usr/bin/env python3
"""CP3.5: trusted GitHub Actions integration of a native-verified-patch.

Only a completed, successful native workflow run in this repository can supply
the patch. Never read/decrypt the hidden oracle, execute proposal code, merge,
approve or apply ready-to-merge. Testable with an injected API transport.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
import zipfile

REPOSITORY = "paulozterra/lf-programming-sandbox"
WORKFLOW = ".github/workflows/worker-native.yml"
ARTIFACTS = {"native-verified-patch": ("worker.patch", 1_000_000),
             "native-visible-feedback-and-cost": ("status.json", 32_000),
             "native-attempt-proof": ("attempt-proof.json", 32_000)}
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
TASK = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
CHG = re.compile(r"CHG-(\d{4})")


class IntegrationBlocked(ValueError):
    pass


def block(reason: str):
    raise IntegrationBlocked("CP35_" + reason)


def sanitized_stderr(stderr: bytes) -> str:
    """A short actionable diagnostic, never credentials or untrusted control bytes."""
    message = stderr.decode("utf-8", errors="replace")
    for key in ("GH_TOKEN", "GITHUB_TOKEN", "GITHUB_PERSONAL_ACCESS_TOKEN",
                "GIT_ASKPASS", "PILOT_HOLDOUT_AGE_KEY"):
        secret = os.environ.get(key, "")
        if len(secret) >= 4:
            message = message.replace(secret, "[REDACTED]")
    # Scrub common GitHub credential formats even when not in our env.
    message = re.sub(r"(?i)Bearer\\s+[^\\s,;]+", "Bearer [REDACTED]", message)
    message = re.sub(r"(?i)(?:gh[pousr]_|github_pat_)[a-zA-Z0-9_]+", "[REDACTED]", message)
    message = re.sub(r"(?i)(https?://)[^\\s/@]+@",
                     r"\\1[REDACTED]@", message)
    message = re.sub(r"[\\x00-\\x1f\\x7f]+", " ", message).strip()
    return message[:1200] or "(empty stderr)"


def command(args: list[str], *, cwd: Path | None = None,
            input_bytes: bytes | None = None, check: bool = True) -> bytes:
    result = subprocess.run(args, cwd=cwd, input=input_bytes, capture_output=True,
                            timeout=120)
    if check and result.returncode:
        tool = Path(args[0]).name
        if tool in ("gh", "git"):
            block("COMMAND_FAILED:" + tool + ":" + sanitized_stderr(result.stderr))
        block("COMMAND_FAILED:" + tool)
    return result.stdout


def gh_api(path: str) -> bytes:
    return command(["gh", "api", "--header", "Accept: application/vnd.github+json", path])


def obj(raw: bytes) -> dict:
    try:
        value = json.loads(raw)
    except (UnicodeError, ValueError):
        block("JSON_INVALID")
    if not isinstance(value, dict):
        block("JSON_INVALID")
    return value


def extract_exact_zip_bundle(raw: bytes, expected: dict[str, int]) -> dict[str, bytes]:
    """Exact, bounded Actions artifact ZIP inventory (no extra or duplicate files).

    The native Worker deliberately uploads three visible-only receipts in one
    artifact. Inspect all of them while still denying traversal and symlinks.
    """
    if not expected or len(raw) > sum(expected.values()) + 300_000:
        block("ARTIFACT_OVERSIZE")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            infos = archive.infolist()
            if (len(infos) != len(expected)
                    or {member.filename for member in infos} != set(expected)):
                block("ARTIFACT_INVENTORY_INVALID")
            result = {}
            for member in infos:
                mode = (member.external_attr >> 16) & 0o170000
                if member.is_dir() or mode not in (0, 0o100000) or member.flag_bits & 1:
                    block("ARTIFACT_NOT_REGULAR_FILE")
                if not 0 < member.file_size <= expected[member.filename]:
                    block("ARTIFACT_SIZE_INVALID")
                value = archive.read(member)
                if len(value) != member.file_size:
                    block("ARTIFACT_BYTES_INVALID")
                result[member.filename] = value
            return result
    except (zipfile.BadZipFile, OSError, RuntimeError):
        block("ARTIFACT_ARCHIVE_INVALID")


def extract_exact_zip(raw: bytes, expected: str, limit: int) -> bytes:
    """Backward-compatible strict single-file extractor."""
    return extract_exact_zip_bundle(raw, {expected: limit})[expected]

def verify_run(run: dict, jobs: dict, expected_run: int) -> None:
    if (run.get("id") != expected_run or run.get("conclusion") != "success"
            or run.get("status") != "completed"
            or run.get("run_attempt") != 1
            or run.get("event") not in ("workflow_run", "workflow_dispatch")
            or run.get("head_branch") != "main"
            or run.get("repository", {}).get("full_name") != REPOSITORY
            or run.get("path", "").split("@")[0] != WORKFLOW):
        block("NATIVE_RUN_UNTRUSTED")
    native = [job for job in jobs.get("jobs", [])
              if job.get("name") == "native" and job.get("conclusion") == "success"]
    if len(native) != 1:
        block("NATIVE_JOB_NOT_SUCCESS")


def get_verified_patch(run_id: int) -> tuple[bytes, dict, dict]:
    run = obj(gh_api(f"repos/{REPOSITORY}/actions/runs/{run_id}"))
    jobs = obj(gh_api(f"repos/{REPOSITORY}/actions/runs/{run_id}/jobs?per_page=100"))
    verify_run(run, jobs, run_id)
    inventory = obj(gh_api(f"repos/{REPOSITORY}/actions/runs/{run_id}/artifacts?per_page=100"))
    entries = inventory.get("artifacts", [])
    raw = {}
    for name, (file, limit) in ARTIFACTS.items():
        found = [a for a in entries if a.get("name") == name and not a.get("expired")]
        if len(found) != 1:
            block("NATIVE_ARTIFACT_MISSING_OR_DUPLICATED")
        archive = gh_api(f"repos/{REPOSITORY}/actions/artifacts/{found[0]['id']}/zip")
        expected = ({"status.json": 32_000, "feedback.json": 32_000,
                     "cost.json": 32_000}
                    if name == "native-visible-feedback-and-cost"
                    else {file: limit})
        raw[name] = extract_exact_zip_bundle(archive, expected)
    status = obj(raw["native-visible-feedback-and-cost"]["status.json"])
    # All three native receipts are present, parseable and unmodified.
    obj(raw["native-visible-feedback-and-cost"]["feedback.json"])
    obj(raw["native-visible-feedback-and-cost"]["cost.json"])
    proof = obj(raw["native-attempt-proof"]["attempt-proof.json"])
    if (status.get("schema_version") != "LF_NATIVE_RESULT_SUMMARY_V1"
            or status.get("status") != "PASS" or status.get("production_authority") is not False
            or status.get("receipt_authenticated") is not False
            or status.get("authority") != "REAL_SANDBOX_UNAUTHENTICATED"
            or status.get("task_id") != proof.get("task_id")
            or status.get("attempt") != proof.get("attempt")
            or proof.get("run_id") != run_id
            or status.get("task_pack_sha256") != proof.get("task_pack_sha256")):
        block("NATIVE_PASS_PROOF_MISMATCH")
    task = status["task_id"]
    if not isinstance(task, str) or not TASK.fullmatch(task):
        block("NATIVE_TASK_UNSAFE")
    return raw["native-verified-patch"]["worker.patch"], status, proof


def allowed_paths(reg: dict) -> tuple[str, set[str]]:
    spec = reg.get("task_spec")
    if not isinstance(spec, dict):
        block("TASK_REGISTRATION_INVALID")
    base = spec.get("base_head_sha")
    paths = spec.get("write_path_patterns")
    if (not isinstance(base, str) or not SHA40.fullmatch(base)
            or not isinstance(paths, list) or not paths or len(paths) > 6):
        block("TASK_SCOPE_INVALID")
    safe = set()
    for name in paths:
        if (not isinstance(name, str) or not name
                or name.startswith(("/", ".github/", "vendor/", "pilot/", "standards/"))
                or "\\" in name or "*" in name or "?" in name
                or PurePosixPath(name).as_posix() != name
                or any(part in ("..", ".") for part in PurePosixPath(name).parts)
                or not name.startswith(("apps/", "backend/", "frontend/", "db/", "supabase/migrations/"))):
            block("TASK_SCOPE_UNSAFE")
        safe.add(name)
    if len(safe) != len(paths):
        block("TASK_SCOPE_DUPLICATE")
    return base, safe


def validate_patch_against_repo(root: Path, patch: bytes, base: str,
                                allowed: set[str]) -> dict[str, str]:
    if not patch or len(patch) > 1_000_000 or b"\x00" in patch:
        block("PATCH_BYTES_INVALID")
    main = command(["git", "rev-parse", "HEAD"], cwd=root).decode().strip()
    if command(["git", "status", "--porcelain"], cwd=root):
        block("WORKTREE_DIRTY")
    command(["git", "merge-base", "--is-ancestor", base, main], cwd=root)
    changed_since = command(["git", "diff", "--name-only", base, main, "--", *sorted(allowed)],
                            cwd=root).decode().splitlines()
    if changed_since:
        block("TASK_BASE_STALE")
    command(["git", "apply", "--check", "--index", "-"], cwd=root, input_bytes=patch)
    command(["git", "apply", "--index", "-"], cwd=root, input_bytes=patch)
    statuses = command(["git", "diff", "--cached", "--name-status", "-z"], cwd=root).decode()
    fields = list(filter(None, statuses.split("\x00")))
    if len(fields) < 2 or len(fields) % 2:
        block("PATCH_SCOPE_INVALID")
    changed = {}
    for i in range(0, len(fields), 2):
        state, path = fields[i:i+2]
        if path not in allowed or state not in ("A", "M"):
            block("PATCH_SCOPE_INVALID")
        data = command(["git", "show", ":" + path], cwd=root)
        changed[path] = hashlib.sha256(data).hexdigest()
    if not changed:
        block("PATCH_EMPTY")
    return changed


def chg_payload(number: int, task: str, run_id: int, patch_sha: str,
                paths: list[str]) -> dict:
    ident = f"CHG-{number:04d}"
    return {
        "schema_version": "LF_STANDARD_CHANGE_V1",
        "change_id": ident,
        "title": f"CP3.5: integración verificada nativa {task} (run {run_id})",
        "change_class": "EDITORIAL",
        "trigger": {"kind": "OWNER", "reference":
                    "CP3.5 autorizado por Paulo; PR draft automático de PASS nativo"},
        "reason": f"Parche originado exclusivamente en native-verified-patch de la corrida "
                  f"nativa PASS {run_id}, SHA-256 {patch_sha}; rutas y bytes aplicados "
                  f"sin reconstruir propuesta, sin exámenes ni aprobación automática.",
        "artifacts": [],
        "affected": {"rule_ids": [], "term_ids": [],
                     "paths": sorted(paths + [f"standards/changes/{ident}.json",
                                             "standards/CAMBIOS.md"])},
        "existing_code_impact": {"mode": "NEW_OR_MODIFIED_ONLY",
                                  "baseline_ref": "standards/baseline/",
                                  "expected_direction": "NON_INCREASING"},
        "security_pin_invalidation": {"invalidates": False, "affected_artifacts": []},
        "requested_by": "agent:gpt", "approved_by": "paulozterra",
        "evidence": {"pr_url": ""},
    }


def next_chg(root: Path) -> int:
    used = [int(p.stem[4:]) for p in (root / "standards/changes").glob("CHG-????.json")]
    # Avoid any CHG already advertised in an open PR (concurrent work).
    pulls = json.loads(command(["gh", "pr", "list", "--repo", REPOSITORY,
                               "--state", "open", "--limit", "100",
                               "--json", "title"], cwd=root))
    for pr in pulls:
        used.extend(int(n) for n in CHG.findall(pr.get("title", "")))
    return max(used + [57]) + 1


def record_change(root: Path, number: int, task: str,
                  run_id: int, patch_sha: str, paths: list[str]) -> Path:
    dest = root / f"standards/changes/CHG-{number:04d}.json"
    if dest.exists():
        block("CHG_COLLISION")
    payload = chg_payload(number, task, run_id, patch_sha, paths)
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", "utf-8")
    command(["python3", "standards/tools/changes.py", "render"], cwd=root)
    return dest


def confirm_class_after_commit(root: Path, chg: Path, base_ref: str = "origin/main") -> None:
    """C9 compares base with HEAD, therefore check only AFTER committing."""
    for attempt in range(2):
        process = subprocess.run(
            ["python3", "standards/tools/changes.py", "check",
             "--base", base_ref], cwd=root, capture_output=True)
        if process.returncode == 0:
            return
        try:
            result = json.loads(process.stdout)
        except (UnicodeError, ValueError):
            block("C9_CHECK_INVALID")
        errors = {item.get("reason_code") for item in result.get("findings", [])}
        classes = result.get("detected_class", [])
        if (errors != {"CHANGE_CLASS_MISMATCH"} or len(classes) != 1
                or classes[0] not in ("ADDITIVE", "EDITORIAL") or attempt):
            block("C9_CHECK_FAILED")
        payload = obj(chg.read_bytes())
        payload["change_class"] = classes[0]
        chg.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", "utf-8")
        command(["python3", "standards/tools/changes.py", "render"], cwd=root)
        command(["git", "add", "--", str(chg.relative_to(root)),
                 "standards/CAMBIOS.md"], cwd=root)
        command(["git", "commit", "-m", "CP3.5: align C9 detected change class"], cwd=root)
    block("C9_CHECK_FAILED")


def assert_existing_tree(root: Path, remote_sha: str, expected_tree: str) -> None:
    """Strict full-tree comparison; never trust branch names or only the SQL path."""
    if not SHA40.fullmatch(remote_sha) or not SHA40.fullmatch(expected_tree):
        block("BRANCH_EXISTS_DIFFERENT")
    actual = command(["git", "rev-parse", remote_sha + "^{tree}"], cwd=root).decode().strip()
    if actual != expected_tree:
        block("BRANCH_EXISTS_DIFFERENT")


def reuse_identical_branch(root: Path, branch: str, remote_sha: str,
                           patch: bytes, base: str, allowed: set[str],
                           task: str, run_id: int) -> tuple[dict[str, str], int]:
    """Replay on the branch's historical main base; compare *entire* Git trees.

    This also works when trusted main advanced after a failed PR publication:
    no rewrite, force push or implicit rebase of the original verified branch.
    """
    if not SHA40.fullmatch(remote_sha):
        block("BRANCH_EXISTS_DIFFERENT")
    command(["git", "fetch", "--no-tags", "origin", remote_sha], cwd=root)
    main = command(["git", "rev-parse", "HEAD"], cwd=root).decode().strip()
    historic = command(["git", "merge-base", main, remote_sha], cwd=root).decode().strip()
    command(["git", "merge-base", "--is-ancestor", base, historic], cwd=root)
    # A remote merge or extra source edit is never considered resumable.
    history = command(["git", "rev-list", "--parents", historic + ".." + remote_sha],
                      cwd=root).decode().splitlines()
    if not 1 <= len(history) <= 3 or any(len(line.split()) != 2 for line in history):
        block("BRANCH_EXISTS_DIFFERENT")
    paths = set(command(["git", "diff", "--name-only", historic, remote_sha],
                        cwd=root).decode().splitlines())
    chgs = [p for p in paths if re.fullmatch(r"standards/changes/CHG-\\d{4}\\.json", p)]
    if len(chgs) != 1 or paths != allowed | {"standards/CAMBIOS.md", chgs[0]}:
        block("BRANCH_EXISTS_DIFFERENT")
    number = int(CHG.fullmatch(Path(chgs[0]).stem).group(1))
    if command(["git", "ls-tree", main, "--", chgs[0]], cwd=root).strip():
        block("BRANCH_EXISTS_DIFFERENT")
    with tempfile.TemporaryDirectory(prefix="cp35-replay-") as temporary:
        replay = Path(temporary) / "source"
        command(["git", "worktree", "add", "--detach", str(replay), historic], cwd=root)
        try:
            changed = validate_patch_against_repo(replay, patch, base, allowed)
            chg = record_change(replay, number, task, run_id,
                                hashlib.sha256(patch).hexdigest(), list(changed))
            command(["git", "add", "--", str(chg.relative_to(replay)),
                     "standards/CAMBIOS.md"], cwd=replay)
            command(["git", "commit", "-m", "CP3.5 deterministic replay"], cwd=replay)
            confirm_class_after_commit(replay, chg, base_ref=historic)
            expected_tree = command(["git", "rev-parse", "HEAD^{tree}"],
                                    cwd=replay).decode().strip()
            assert_existing_tree(root, remote_sha, expected_tree)
        finally:
            command(["git", "worktree", "remove", "--force", str(replay)], cwd=root)
    return changed, number


def publish(root: Path, run_id: int, patch: bytes, status: dict, proof: dict) -> dict:
    task = status["task_id"]
    reg_path = root / f"pilot/worker_v08/native_tasks/{task}.json"
    if reg_path.is_symlink() or not reg_path.is_file():
        block("NATIVE_TASK_UNREGISTERED")
    reg = obj(reg_path.read_bytes())
    base, allowed = allowed_paths(reg)
    if (status.get("task_pack_sha256") != proof.get("task_pack_sha256")
            or not SHA64.fullmatch(status.get("proposal_sha256", ""))):
        block("NATIVE_PROOF_INVALID")
    main = command(["git", "rev-parse", "HEAD"], cwd=root).decode().strip()
    if main != command(["git", "rev-parse", "origin/main"], cwd=root).decode().strip():
        block("MAIN_NOT_CURRENT")
    branch = f"lf/native-integration/{task}-run-{run_id}"
    remote = command(["git", "ls-remote", "--heads", "origin", branch], cwd=root)
    patch_hash = hashlib.sha256(patch).hexdigest()
    if remote:
        remote_sha = remote.decode().split()[0]
        changed, num = reuse_identical_branch(
            root, branch, remote_sha, patch, base, allowed, task, run_id)
        # Reuse exact source tree as verified. Never recreate or overwrite it.
        command(["git", "switch", "-c", branch, remote_sha], cwd=root)
        assert_existing_tree(root, remote_sha,
                             command(["git", "rev-parse", "HEAD^{tree}"],
                                     cwd=root).decode().strip())
        chg = root / f"standards/changes/CHG-{num:04d}.json"
    else:
        changed = validate_patch_against_repo(root, patch, base, allowed)
        num = next_chg(root)
        chg = record_change(root, num, task, run_id, patch_hash, list(changed))
        command(["git", "add", "--", str(chg.relative_to(root)),
                 "standards/CAMBIOS.md"], cwd=root)
        command(["python3", "standards/tools/changes.py", "render", "--check"],
                cwd=root)
        current_remote = command(["git", "ls-remote", "origin", "refs/heads/main"],
                                 cwd=root).decode().split()[0]
        if current_remote != main:
            block("MAIN_MOVED_BEFORE_PUBLICATION")
        command(["git", "switch", "-c", branch], cwd=root)
        command(["git", "commit", "-m",
                 f"[CP3.5][CHG-{num:04d}] verified native patch {task} run {run_id}"],
                cwd=root)
        confirm_class_after_commit(root, chg)
        command(["git", "push", "--set-upstream", "origin", branch], cwd=root)
    body = (f"CP3.5: PASS verificado por workflow nativo confiable.\n\n"
            f"- Task: \`{task}\` · run: {run_id} · base: \`{base}\`\n"
            f"- Native patch SHA-256: \`{patch_hash}\`\n"
            f"- Source files SHA-256 after exact application: "
            + json.dumps(changed, sort_keys=True) + "\n"
            f"- CHG-{num:04d}; sin etiquetado ni merge automático. "
            f"Claude revisa; Paulo aplica ready-to-merge.\n")
    url = command(["gh", "pr", "create", "--repo", REPOSITORY, "--base", "main",
                   "--head", branch, "--draft",
                   "--title", f"[DRAFT][CP3.5][CHG-{num:04d}] Verified native {task} run {run_id}",
                   "--body", body], cwd=root).decode().strip()
    payload = obj(chg.read_bytes())
    payload["evidence"]["pr_url"] = url
    chg.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", "utf-8")
    command(["python3", "standards/tools/changes.py", "render"], cwd=root)
    command(["python3", "standards/tools/changes.py", "check", "--base", "origin/main"], cwd=root)
    command(["git", "add", "--", str(chg.relative_to(root)), "standards/CAMBIOS.md"], cwd=root)
    command(["git", "commit", "-m", f"[CP3.5][CHG-{num:04d}] record PR evidence"], cwd=root)
    command(["git", "push", "origin", branch], cwd=root)
    final_head = command(["git", "rev-parse", "HEAD"], cwd=root).decode().strip()
    # GITHUB_TOKEN-created PR events do not reliably start CI. Dispatch exactly
    # once, by the final HEAD branch; the Train verifies exact HEAD checks.
    command(["gh", "workflow", "run", "ci.yml", "--repo", REPOSITORY,
             "--ref", branch], cwd=root)
    return {"pr_url": url, "branch": branch, "head_sha": final_head,
            "run_id": run_id, "patch_sha256": patch_hash, "files_sha256": changed,
            "merge_authorized": False}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", type=int, required=True)
    p.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = p.parse_args()
    if args.run_id <= 0 or os.environ.get("GITHUB_REPOSITORY") != REPOSITORY:
        block("RUN_ID_OR_REPOSITORY_INVALID")
    try:
        patch, status, proof = get_verified_patch(args.run_id)
        print(json.dumps(publish(args.root, args.run_id, patch, status, proof),
                         sort_keys=True))
    except (IntegrationBlocked, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(str(exc) if isinstance(exc, IntegrationBlocked) else "CP35_INTEGRATION_BLOCKED",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
