#!/usr/bin/env python3
"""Build a reproducible, non-authoritative evidence bundle from real ex5c Git and CI.

Source checkout is pinned to a Git commit. Worker receipts are public,
sanitized Run C artifacts. NEVER retrieve private/oracle artifacts.
"""
from __future__ import annotations
import base64
import hashlib
import io
import json
import os
import re
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
COMMIT = "e76b213cb2f367f787e0eba3bf8ff74136edd883"
BASE = "28de535acd4a76be038013cc6241c59a08102155"
EXPECTED_TREE = "922f74a8ffaab9b8233625c804b8c92a17d8b8a3"
EXPECTED_SUBTREE = "4ba97b68310e913795d7ae1ac35d5912e2fe6551"
EXPECTED_BASE_SUBTREE = "91ac08b61d4fbb20d47dacc698778def71f2c805"
EXPECTED_PATCH = "bfba0329bcac92dbde06a1319a16acd535acd718f224df6121dae3c70fe307c6"
EXPECTED_CONTEXT = "23e4c00d387ae34a111b98994f00d9965eefd7886f5b945e892f9451d59b1cc4"
EXPECTED_CONTEXT_INNER = "9cc719ef41a3b9e70d21b94780e0b17a6887fb57b4683eeaaf3157c2a1cb676d"
RUN_ID = 42284754122
ARTIFACTS = {"worker-pilot-receipts-cost-logs", "worker-pilot-verified-patch"}
RECEIPTS = ("verified-worker-receipt.json", "visible-worker-receipt.json", "cost.json", "derived-context.json")
REQS = {"REM-C1", "REM-C2", "REM-C3", "REM-C4", "REM-C5", "REM-C6", "REM-C7"}


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def git(*args: str, inp: bytes | None = None) -> bytes:
    r = subprocess.run(["git", "-C", str(ROOT), *args], input=inp, capture_output=True, timeout=60)
    if r.returncode:
        raise ValueError("GIT_VERIFICATION_BLOCKED:" + " ".join(args[:3]))
    return r.stdout


def git_oid(kind: str, content: bytes) -> str:
    raw = (kind + " " + str(len(content)) + "\0").encode() + content
    return hashlib.sha1(raw).hexdigest()


def b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def require(ok: bool, code: str) -> None:
    if not ok:
        raise ValueError(code)


def api_bytes(url: str, token: str) -> bytes:
    require(url.startswith("https://api.github.com/"), "EXTERNAL_URL_FORBIDDEN")
    request = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "lf-evidence-bundle-ex5c"
    })
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def load_run_artifacts() -> dict[str, bytes]:
    token = os.environ.get("GH_TOKEN", "")
    require(bool(token), "GH_READ_TOKEN_UNAVAILABLE")
    base_url = "https://api.github.com/repos/paulozterra/lf-programming-sandbox"
    run = json.loads(api_bytes(base_url + "/actions/runs/" + str(RUN_ID), token))
    require(run.get("head_sha") == "5b5f860f2c142c9741a4dfad93f25bf4914c710d"
            and run.get("conclusion") == "success" and run.get("run_attempt") == 1,
            "REAL_RUN_BINDING_INVALID")
    manifest = json.loads(api_bytes(base_url + "/actions/runs/" + str(RUN_ID) + "/artifacts?per_page=100", token))
    found = {a["name"]: a for a in manifest.get("artifacts", []) if a.get("name") in ARTIFACTS}
    require(set(found) == ARTIFACTS and all(not a.get("expired") for a in found.values()),
            "REAL_RUN_ARTIFACTS_MISSING")
    result: dict[str, bytes] = {}
    for name in sorted(found):
        # GitHub redirects binary downloads to its signed object storage URL.
        url = base_url + "/actions/artifacts/" + str(found[name]["id"]) + "/zip"
        with zipfile.ZipFile(io.BytesIO(api_bytes(url, token))) as archive:
            for item in archive.namelist():
                if item in RECEIPTS or item == "worker.patch" or item == "derived-context.sha256":
                    require(item not in result, "DUPLICATE_RECEIPT_NAME")
                    require(not item.startswith("/") and ".." not in Path(item).parts,
                            "INVALID_ARTIFACT_PATH")
                    result[item] = archive.read(item)
    require(set(RECEIPTS) | {"worker.patch", "derived-context.sha256"} == set(result),
            "REQUIRED_PUBLIC_RECEIPTS_MISSING")
    require(sha(result["worker.patch"]) == EXPECTED_PATCH, "WORKER_PATCH_SHA_MISMATCH")
    require(sha(result["derived-context.json"]) == EXPECTED_CONTEXT, "DERIVED_CONTEXT_SHA_MISMATCH")
    require(result["derived-context.sha256"].decode("utf-8").strip() ==
            EXPECTED_CONTEXT + "  derived-context.json", "DERIVED_CONTEXT_SIDECAR_MISMATCH")
    return result


def git_evidence() -> tuple[dict, list[dict], bytes]:
    require(git("rev-parse", "HEAD").strip().decode() == COMMIT, "WRONG_CHECKOUT_HEAD")
    tree = git("rev-parse", COMMIT + "^{tree}").decode().strip()
    subtree = git("rev-parse", COMMIT + ":apps/time-service").decode().strip()
    base_subtree = git("rev-parse", BASE + ":apps/time-service").decode().strip()
    require((tree, subtree, base_subtree) ==
            (EXPECTED_TREE, EXPECTED_SUBTREE, EXPECTED_BASE_SUBTREE),
            "GIT_TREE_BINDING_BLOCKED")
    raw = git("cat-file", "commit", COMMIT)
    require(git_oid("commit", raw) == COMMIT, "GIT_COMMIT_OBJECT_MISMATCH")
    parents = [p.split(" ", 1)[1] for p in raw.decode("utf-8", errors="replace").splitlines()
               if p.startswith("parent ")]
    require(parents == ["5b5f860f2c142c9741a4dfad93f25bf4914c710d",
                        "7829300aeb615d8243bb2ca45a82705939fcd8cf"],
            "GIT_PARENTS_MISMATCH")
    rows = git("ls-tree", "-r", "-z", COMMIT, "--", "apps/time-service").split(b"\0")
    files = []
    for item in rows:
        if not item:
            continue
        meta, path = item.split(b"\t", 1)
        mode, kind, oid = meta.decode().split(" ")
        require(kind == "blob" and mode == "100644", "UNEXPECTED_GIT_ENTRY")
        name = path.decode("utf-8")
        raw_file = git("show", COMMIT + ":" + name)
        require(git_oid("blob", raw_file) == oid, "GIT_BLOB_OID_MISMATCH")
        files.append({"path": name, "mode": mode, "oid": oid,
                      "bytes": len(raw_file), "content_base64": b64(raw_file)})
    require(len(files) == 18 and sum(x["bytes"] for x in files) == 29347,
            "SUBTREE_FILE_INVENTORY_MISMATCH")
    files.sort(key=lambda x: x["path"].encode("utf-8"))
    # Rebuild Git trees recursively from all 18 file blobs, not just compare a report.
    root = {}
    for row in files:
        parts = row["path"].removeprefix("apps/time-service/").split("/")
        cur = root
        for part in parts[:-1]:
            cur = cur.setdefault(part, {})
        cur[parts[-1]] = (row["mode"], row["oid"])
    def tree_oid(node: dict) -> str:
        entries = []
        for name, item in node.items():
            if isinstance(item, dict):
                mode, oid = "40000", tree_oid(item)
            else:
                mode, oid = item
            entries.append((name, mode, oid))
        entries.sort(key=lambda x: (x[0] + ("/" if x[1] == "40000" else "")).encode())
        raw_tree = b"".join(mode.encode() + b" " + name.encode() + b"\0" +
                            bytes.fromhex(oid) for name, mode, oid in entries)
        return git_oid("tree", raw_tree)
    require(tree_oid(root) == EXPECTED_SUBTREE, "REBUILT_SUBTREE_OID_MISMATCH")
    return ({"commit": COMMIT, "tree": tree, "parents": parents, "subtree_oid": subtree,
             "base_commit": BASE, "base_subtree_oid": base_subtree,
             "raw_commit_base64": b64(raw), "raw_commit_sha256": sha(raw)}, files, raw)


def patch_evidence(worker: bytes) -> dict:
    patch = git("diff", BASE, COMMIT, "--", "apps/time-service/src/main")
    require(patch == worker, "REAL_GIT_DIFF_NOT_WORKER_PATCH")
    require(sha(patch) == EXPECTED_PATCH, "REAL_GIT_DIFF_SHA_MISMATCH")
    path = None
    hunks: list[dict] = []
    current: list[bytes] = []
    def add_hunk():
        if current:
            raw = b"".join(current)
            header = raw.split(b"\n", 1)[0].decode("utf-8")
            hunks.append({"path": path, "header": header, "sha256": sha(raw),
                          "bytes": len(raw), "content_base64": b64(raw)})
    for line in patch.splitlines(keepends=True):
        if line.startswith(b"diff --git "):
            add_hunk()
            current = []
            path = line.decode().strip().split(" b/", 1)[1]
        elif line.startswith(b"@@ "):
            add_hunk()
            current = [line]
        elif current:
            current.append(line)
    add_hunk()
    mapping = json.loads((HERE / "hunk_requirements.json").read_text(encoding="utf-8"))
    require(mapping.get("schema_version") == "LF_EX5C_HUNK_REQUIREMENTS_V1" and
            mapping.get("base_commit") == BASE and mapping.get("candidate_commit") == COMMIT,
            "HUNK_MAPPING_SCHEMA_INVALID")
    by_key = {(x["path"], x["header"]): x["requirements"] for x in mapping.get("mapping", [])}
    require(len(by_key) == len(hunks) == len(mapping.get("mapping", [])), "HUNK_COVERAGE_MISMATCH")
    seen = set()
    for item in hunks:
        key = (item["path"], item["header"])
        reqs = by_key.get(key)
        require(isinstance(reqs, list) and bool(reqs) and set(reqs) <= REQS,
                "HUNK_REQUIREMENT_MISSING")
        item["requirements"] = reqs
        seen.update(reqs)
    require(seen == REQS, "CODE_REQUIREMENT_UNCOVERED")
    return {"text_base64": b64(patch), "sha256": sha(patch),
            "worker_patch_sha256": sha(worker), "bytes": len(patch),
            "hunks": hunks, "mapping_sha256": sha((HERE / "hunk_requirements.json").read_bytes())}


def command_evidence(argv: list[str], *, timeout: int = 900) -> dict:
    start = time.monotonic_ns()
    proc = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=timeout)
    duration = (time.monotonic_ns() - start) // 1_000_000
    return {"argv": argv, "exit_code": proc.returncode, "duration_ms": duration,
            "stdout": {"base64": b64(proc.stdout), "bytes": len(proc.stdout), "sha256": sha(proc.stdout)},
            "stderr": {"base64": b64(proc.stderr), "bytes": len(proc.stderr), "sha256": sha(proc.stderr)},
            "result": "PASS" if proc.returncode == 0 else "FAIL"}


def smoke() -> dict:
    jars = [p for p in (ROOT / "apps/time-service/target").glob("time-service-*.jar")
            if not p.name.endswith((".original", ".sources.jar", ".javadoc.jar"))]
    require(len(jars) == 1, "BUILT_JAR_NOT_UNIQUE")
    jar = jars[0]
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    argv = ["java", "-jar", str(jar), "--server.address=127.0.0.1", "--server.port=" + str(port)]
    events = []
    with tempfile.TemporaryDirectory(prefix="lf_ex5c_smoke_") as tmp:
        out_path, err_path = Path(tmp) / "java.stdout", Path(tmp) / "java.stderr"
        with out_path.open("wb") as out, err_path.open("wb") as err:
            proc = subprocess.Popen(argv, cwd=ROOT, stdout=out, stderr=err)
            def request(method: str, endpoint: str, data: bytes | None = None) -> tuple[int, bytes, dict]:
                headers = {"Content-Type": "application/json"} if data is not None else {}
                r = urllib.request.Request("http://127.0.0.1:" + str(port) + endpoint,
                                           data=data, method=method, headers=headers)
                try:
                    with urllib.request.urlopen(r, timeout=5) as x:
                        return x.status, x.read(), dict(x.headers.items())
                except urllib.error.HTTPError as x:
                    return x.code, x.read(), dict(x.headers.items())
            def step(name: str, method: str, endpoint: str, expected: int, data: bytes | None = None):
                code, body, headers = request(method, endpoint, data)
                events.append({"step": name, "method": method, "path": endpoint,
                               "request_body_base64": b64(data) if data is not None else None,
                               "status": code, "body_sha256": sha(body),
                               "body_bytes": len(body), "body_base64": b64(body)})
                require(code == expected, "SMOKE_" + name + "_STATUS_BLOCKED")
                return headers
            try:
                deadline = time.monotonic() + 60
                while True:
                    try:
                        code, _, _ = request("GET", "/api/time")
                        if code == 200:
                            break
                    except (urllib.error.URLError, TimeoutError, ConnectionError):
                        pass
                    require(proc.poll() is None and time.monotonic() < deadline,
                            "JAVA_SERVICE_DID_NOT_START")
                    time.sleep(0.25)
                step("healthcheck", "GET", "/api/time", 200)
                location = step("create", "POST", "/api/reminders", 201,
                                b'{"text":"EvidenceEx5cUnique","at":"13:20:30"}').get("Location")
                require(bool(location) and location.startswith("/api/reminders/"),
                        "SMOKE_LOCATION_INVALID")
                step("search", "GET", "/api/reminders?q=evidenceex5c", 200)
                step("delete", "DELETE", location, 204)
                step("get_after_delete", "GET", location, 404)
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
        stdout, stderr = out_path.read_bytes(), err_path.read_bytes()
    return {"argv": ["java", "-jar", "apps/time-service/target/" + jar.name,
                     "--server.address=127.0.0.1", "--server.port=<ephemeral>"],
            "jar_sha256": sha(jar.read_bytes()), "jar_bytes": jar.stat().st_size,
            "steps": events,
            "stdout": {"base64": b64(stdout), "sha256": sha(stdout), "bytes": len(stdout)},
            "stderr": {"base64": b64(stderr), "sha256": sha(stderr), "bytes": len(stderr)}}


def worker_evidence(raw: dict[str, bytes]) -> dict:
    verified = json.loads(raw["verified-worker-receipt.json"])
    visible = json.loads(raw["visible-worker-receipt.json"])
    cost = json.loads(raw["cost.json"])
    context = json.loads(raw["derived-context.json"])
    require(verified.get("status") == "PASS" and verified.get("visible_status") == "PASS"
            and verified.get("task_id") == "LF-WORKER-PILOT-REAL-005C"
            and verified.get("base_head_sha") ==
                "5b5f860f2c142c9741a4dfad93f25bf4914c710d",
            "PUBLIC_WORKER_VERDICT_INVALID")
    require(visible.get("requested_model") == "claude-sonnet-5-5" and
            verified.get("resolved_model") == "claude-sonnet-5-5",
            "REAL_WORKER_MODEL_MISMATCH")
    require(context.get("sha256") == EXPECTED_CONTEXT_INNER and
            context.get("bytes") == 18254 and len(context.get("files", [])) == 10,
            "REAL_CONTEXT_STRUCTURE_MISMATCH")
    require(str(cost.get("total_estimated_usd")) == "0.070022",
            "REAL_REPORTED_COST_MISMATCH")
    return {
        "run_id": RUN_ID, "evidence_kind": "REAL_SANDBOX_UNAUTHENTICATED",
        "resolved_model": verified["resolved_model"],
        "receipt_authenticated": False, "tool_execution_verified": False,
        "production_authority": False, "worker_invoked": False,
        "files": {name: {"sha256": sha(raw[name]), "bytes": len(raw[name]),
                         "content_base64": b64(raw[name])}
                  for name in RECEIPTS},
    }


def main() -> None:
    git_data, files, _ = git_evidence()
    raw = load_run_artifacts()
    patch = patch_evidence(raw["worker.patch"])
    maven = command_evidence(["mvn", "-B", "-f", "apps/time-service/pom.xml", "verify"])
    require(maven["exit_code"] == 0, "MAVEN_VERIFY_FAILED")
    health = smoke()
    bundle = {
        "schema_version": "LF_EX5C_REAL_EVIDENCE_BUNDLE_V1",
        "evidence_kind": "REAL_SANDBOX_UNAUTHENTICATED",
        "production_authority": False,
        "tool_execution_verified": False,
        "receipt_authenticated": False,
        "worker_invoked": False,
        "git": git_data, "files": files, "patch": patch,
        "execution": {"maven": maven, "smoke": health},
        "worker": worker_evidence(raw),
    }
    output = HERE / "lf-evidence-bundle-v1.json"
    require(not output.exists(), "EVIDENCE_OUTPUT_ALREADY_EXISTS")
    output.write_bytes((json.dumps(bundle, sort_keys=True, ensure_ascii=True,
                                   separators=(",", ":")) + "\n").encode("utf-8"))
    sidecar = output.with_suffix(".sha256")
    sidecar.write_text(sha(output.read_bytes()) + "  " + output.name + "\n", encoding="utf-8")
    print("EX5C_REAL_EVIDENCE_BUNDLE_READY sha256=" + sha(output.read_bytes()))
    print("GIT_PATCH_MATCH_WORKER_PATCH=true 18_FILES_29347_BYTES_REBUILT=true")
    print("MAVEN_VERIFY_PASS SMOKE_PASS WORKER_PUBLIC_PASS AUTHORITY_FALSE")


if __name__ == "__main__":
    main()
