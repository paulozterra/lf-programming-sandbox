#!/usr/bin/env python3
"""Reproducible public Ex5C sandbox evidence. No holdout, secrets or LF data."""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import zipfile

TARGET = "e76b213cb2f367f787e0eba3bf8ff74136edd883"
BASE = "28de535acd4a76be038013cc6241c59a08102155"
TREE = "922f74a8ffaab9b8233625c804b8c92a17d8b8a3"
SUBTREE = "4ba97b68310e913795d7ae1ac35d5912e2fe6551"
BASE_SUBTREE = "91ac08b61d4fbb20d47dacc698778def71f2c805"
PATCH_SHA = "bfba0329bcac92dbde06a1319a16acd535acd718f224df6121dae3c70fe307c6"
RUN_ID = 42284754122
ARTIFACT_RECEIPTS = 13537565729
ARTIFACT_PATCH = 13537475831
EXPECTED_CONTEXT_SHA = "9cc719ef41a3b9e70d21b94780e0b17a6887fb57b4683eeaaf3157c2a1cb676d"
RECEIPT_NAMES = ("verified-worker-receipt.json", "visible-worker-receipt.json",
                 "cost.json", "derived-context.json")
HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
DIFF_RE = re.compile(r"^diff --git a/(.*?) b/(.*?)$")

def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

def b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")

def git(*args: str, input: bytes | None = None) -> bytes:
    return subprocess.run(("git", *args), input=input, check=True,
                          capture_output=True).stdout

def enforce(condition: bool, name: str) -> None:
    if not condition:
        raise RuntimeError("EVIDENCE_BLOCK_" + name)

def object_oid(kind: str, raw: bytes) -> str:
    return hashlib.sha1(kind.encode("ascii") + b" " + str(len(raw)).encode("ascii")
                        + b"\0" + raw).hexdigest()

def download_artifact(artifact_id: int) -> dict[str, bytes]:
    # Read-only GitHub CLI uses an existing Actions token without printing it.
    out = subprocess.run(("gh", "api",
                          f"/repos/paulozterra/lf-programming-sandbox/actions/artifacts/{artifact_id}/zip"),
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90)
    enforce(out.returncode == 0 and out.stdout.startswith(b"PK"), "ARTIFACT_DOWNLOAD")
    with zipfile.ZipFile(io.BytesIO(out.stdout)) as z:
        names = z.namelist()
        enforce(len(names) == len(set(names)), "ARTIFACT_DUPLICATE")
        enforce(all(not n.startswith("/") and ".." not in Path(n).parts for n in names),
                "ARTIFACT_PATH")
        return {Path(n).name: z.read(n) for n in names if not n.endswith("/")}

def hunks(patch: bytes, mapping: dict) -> list[dict]:
    lines = patch.decode("utf-8").splitlines(keepends=True)
    found: list[dict] = []
    filename = ""
    current: list[str] = []
    old = new = None
    def finish():
        nonlocal current
        if current:
            match = HUNK_RE.match(current[0])
            enforce(match is not None, "HUNK_HEADER")
            old_start, old_count, new_start, new_count = (
                int(match.group(1)), int(match.group(2) or 1),
                int(match.group(3)), int(match.group(4) or 1))
            h = {"path": filename, "old_start": old_start, "old_count": old_count,
                 "new_start": new_start, "new_count": new_count}
            rows = [r for r in mapping["mappings"] if
                    all(r.get(k) == v for k, v in h.items())]
            enforce(len(rows) == 1, "HUNK_REQUIREMENT_UNMAPPED")
            h["requirements"] = rows[0]["requirements"]
            h["sha256"] = sha("".join(current).encode("utf-8"))
            h["text_base64"] = b64("".join(current).encode("utf-8"))
            found.append(h)
            current = []
    for line in lines:
        m = DIFF_RE.match(line.rstrip("\n"))
        if m:
            finish()
            enforce(m.group(1) == m.group(2), "DIFF_RENAME")
            filename = m.group(2)
        elif line.startswith("@@ "):
            finish()
            current = [line]
        elif current:
            current.append(line)
    finish()
    actual = {(h["path"], h["old_start"], h["new_start"]) for h in found}
    expected = {(h["path"], h["old_start"], h["new_start"]) for h in mapping["mappings"]}
    enforce(actual == expected and len(found) == len(mapping["mappings"]),
            "HUNK_SET_DRIFT")
    reqs = {r for h in found for r in h["requirements"]}
    enforce(reqs == {"REM-C" + str(i) for i in range(1, 8)}, "REQUIREMENT_COVERAGE")
    return found

def build_files() -> tuple[list[dict], int]:
    rows = git("ls-tree", "-r", "-z", TARGET, "--", "apps/time-service").split(b"\0")
    files = []
    for row in rows:
        if not row:
            continue
        meta, path = row.split(b"\t", 1)
        mode, typ, oid = meta.decode("ascii").split(" ")
        enforce(typ == "blob" and mode == "100644", "FILE_MODE")
        name = path.decode("utf-8")
        raw = git("cat-file", "blob", oid)
        enforce(object_oid("blob", raw) == oid, "BLOB_OID")
        files.append({"path": name, "mode": mode, "oid": oid,
                      "bytes": len(raw), "content_base64": b64(raw)})
    files.sort(key=lambda r: r["path"])
    total = sum(f["bytes"] for f in files)
    enforce(len(files) == 18 and total == 29347, "FILE_COUNT_OR_BYTES")
    return files, total

def command_result(argv: list[str]) -> dict:
    started = time.monotonic_ns()
    p = subprocess.run(argv, capture_output=True, timeout=600)
    duration = time.monotonic_ns() - started
    return {"argv": argv, "exit_code": p.returncode,
            "duration_ns": duration,
            "stdout_base64": b64(p.stdout), "stdout_sha256": sha(p.stdout),
            "stdout_bytes": len(p.stdout),
            "stderr_base64": b64(p.stderr), "stderr_sha256": sha(p.stderr),
            "stderr_bytes": len(p.stderr)}

def smoke(jar: Path) -> dict:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    logs = []
    with tempfile.TemporaryDirectory(prefix="ex5c-smoke-") as temp:
        stdout_path, stderr_path = Path(temp) / "java.stdout", Path(temp) / "java.stderr"
        with stdout_path.open("wb") as so, stderr_path.open("wb") as se:
            proc = subprocess.Popen(("java", "-jar", str(jar),
                                    f"--server.port={port}", "--server.address=127.0.0.1"),
                                    stdout=so, stderr=se)
            def req(method: str, url: str, body: bytes | None = None):
                request = urllib.request.Request(
                    f"http://127.0.0.1:{port}{url}", method=method, data=body,
                    headers={"Content-Type": "application/json"} if body is not None else {})
                try:
                    with urllib.request.urlopen(request, timeout=5) as resp:
                        return resp.status, resp.read(), dict(resp.headers)
                except urllib.error.HTTPError as error:
                    return error.code, error.read(), dict(error.headers)
            try:
                deadline = time.monotonic() + 75
                while time.monotonic() < deadline:
                    if proc.poll() is not None:
                        raise RuntimeError("EVIDENCE_BLOCK_SMOKE_SERVER_EXIT")
                    try:
                        code, body, headers = req("GET", "/api/time")
                        if code == 200:
                            break
                    except (OSError, TimeoutError):
                        pass
                    time.sleep(0.4)
                else:
                    raise RuntimeError("EVIDENCE_BLOCK_SMOKE_STARTUP")
                def check(name, method, url, expected, data=None):
                    code, body, headers = req(method, url, data)
                    enforce(code == expected, "SMOKE_" + name.upper())
                    logs.append({"name": name, "method": method, "url": url,
                                 "status": code, "body_sha256": sha(body),
                                 "body_bytes": len(body), "body_base64": b64(body)})
                    return headers
                check("time", "GET", "/api/time", 200)
                headers = check("post", "POST", "/api/reminders", 201,
                                b'{"text":"Ex5C Evidence Needle","at":"13:14:15"}')
                location = headers.get("Location")
                enforce(bool(location and re.fullmatch(r"/api/reminders/\d+", location)),
                        "SMOKE_LOCATION")
                check("search", "GET", "/api/reminders?q=NEEDLE", 200)
                check("delete", "DELETE", location, 204)
                check("not_found", "GET", location, 404)
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
        stdout, stderr = stdout_path.read_bytes(), stderr_path.read_bytes()
    return {"steps": logs, "server_stdout_base64": b64(stdout),
            "server_stdout_sha256": sha(stdout), "server_stdout_bytes": len(stdout),
            "server_stderr_base64": b64(stderr),
            "server_stderr_sha256": sha(stderr), "server_stderr_bytes": len(stderr)}

def build(root: Path) -> dict:
    enforce(git("rev-parse", "HEAD").decode().strip() == TARGET, "CHECKOUT_COMMIT")
    enforce(git("rev-parse", TARGET + "^{tree}").decode().strip() == TREE, "ROOT_TREE")
    enforce(git("rev-parse", TARGET + ":apps/time-service").decode().strip() == SUBTREE,
            "SUBTREE")
    enforce(git("rev-parse", BASE + ":apps/time-service").decode().strip() == BASE_SUBTREE,
            "BASE_SUBTREE")
    commit_raw = git("cat-file", "commit", TARGET)
    enforce(object_oid("commit", commit_raw) == TARGET, "RAW_COMMIT_OID")
    parents = git("rev-list", "--parents", "-n", "1", TARGET).decode().strip().split()[1:]
    enforce(len(parents) == 2, "COMMIT_PARENT_COUNT")
    files, total = build_files()
    patch = git("diff", BASE, TARGET, "--", "apps/time-service/src/main")
    enforce(sha(patch) == PATCH_SHA, "DIFF_SHA")
    mapping = json.loads((root / "evidence/ex5c/hunk_requirements.json").read_text(encoding="utf-8"))
    hunk_list = hunks(patch, mapping)
    art = download_artifact(ARTIFACT_RECEIPTS)
    patch_art = download_artifact(ARTIFACT_PATCH)
    enforce(set(RECEIPT_NAMES).issubset(art), "RECEIPT_FILE_MISSING")
    enforce("worker.patch" in patch_art, "PATCH_ARTIFACT_MISSING")
    worker_patch = patch_art["worker.patch"]
    enforce(sha(worker_patch) == PATCH_SHA and patch == worker_patch, "WORKER_DIFF_MISMATCH")
    reports = {}
    for name in RECEIPT_NAMES:
        raw = art[name]
        reports[name] = {"sha256": sha(raw), "bytes": len(raw),
                         "content_base64": b64(raw)}
    context = json.loads(art["derived-context.json"])
    enforce(context.get("sha256") == EXPECTED_CONTEXT_SHA, "CONTEXT_RECEIPT_SHA")
    verified = json.loads(art["verified-worker-receipt.json"])
    visible = json.loads(art["visible-worker-receipt.json"])
    cost = json.loads(art["cost.json"])
    enforce(verified.get("status") == "PASS"
            and verified.get("visible_status") == "PASS"
            and verified.get("task_id") == "LF-WORKER-PILOT-REAL-005C",
            "WORKER_VERIFIED_STATUS")
    enforce(visible.get("status") == "PASS", "WORKER_VISIBLE_STATUS")
    model = verified.get("resolved_model")
    enforce(model == "claude-sonnet-5-5", "WORKER_MODEL")
    enforce(float(cost["total_estimated_usd"]) <= 0.35, "COST_LIMIT")
    compile_result = command_result(["mvn", "-B", "-f", "apps/time-service/pom.xml", "verify"])
    enforce(compile_result["exit_code"] == 0, "MAVEN_VERIFY")
    candidates = [p for p in Path("apps/time-service/target").glob("time-service-*.jar")
                  if not p.name.endswith(".original") and not p.name.endswith(".sources.jar")]
    enforce(len(candidates) == 1, "JAR_COUNT")
    return {
        "schema_version": "LF_EX5C_EVIDENCE_BUNDLE_V1",
        "evidence_kind": "REAL_SANDBOX_UNAUTHENTICATED",
        "production_authority": False, "tool_execution_verified": False,
        "receipt_authenticated": False,
        "git": {"commit": TARGET, "tree": TREE, "parents": parents,
                "base_commit": BASE, "subtree_oid": SUBTREE,
                "base_subtree_oid": BASE_SUBTREE,
                "raw_commit_base64": b64(commit_raw)},
        "files": files, "file_count": len(files), "file_bytes": total,
        "patch": {"text_base64": b64(patch), "sha256": sha(patch),
                  "worker_patch_sha256": sha(worker_patch),
                  "hunks": hunk_list},
        "worker": {"run_id": RUN_ID, "model_resolved": model,
                   "receipts": reports},
        "execution": {"maven_verify": compile_result,
                      "smoke": smoke(candidates[0])},
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = build(Path.cwd())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(payload, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")) + "\n").encode("utf-8")
    args.output.write_bytes(raw)
    digest = sha(raw)
    (args.output.parent / (args.output.name + ".sha256")).write_text(
        digest + "  " + args.output.name + "\n", encoding="ascii")
    print("EX5C_EVIDENCE_BUNDLE_CREATED sha256=" + digest +
          " files=" + str(payload["file_count"]) +
          " bytes=" + str(payload["file_bytes"]) +
          " hunks=" + str(len(payload["patch"]["hunks"])))

if __name__ == "__main__":
    main()
