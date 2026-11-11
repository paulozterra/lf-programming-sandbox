"""EX5C FORMAT_REMEDIATION N+1 evidence admission, fail closed, no authority.

This module intentionally cannot accept v3 until a real sandbox-generated
SHA-256 is explicitly fixed by a separate governance commit. Reconstructs
raw commit, all Git blobs + subtree, class byte records, stdout/stderr and
HTTP response hashes. Does not authenticate worker or emit PG14 ACCEPT.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path

N = "e76b213cb2f367f787e0eba3bf8ff74136edd883"
V1_SHA = "436bc771ccd04b5eeb407102f7c55a3338bacf43f8f292773f293aa615a8da3b"
V2_SHA = "0988de2e39f5139596d05c3cbfcbe8c8998c753cdb009414e5b38da65172217b"
FORMATTER_SHA = "f2239a8a234a240a54fdff7809d4b3e66702c21f590c77a0b6cf7b20c829e95a"
V3_SHA = "417b504380e4ebe9f4345b2b33c21d6a8f0d0a05b1e51ef2a86de3822bc09ec0"
V3_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/lf-evidence-bundle-v3.json"
EXPECTED_COMMIT = "bc74940727f1bb51a076f52a4b20fb5ed00647c8"
AUTH_KEYS = {"production_authority", "receipt_authenticated",
             "tool_execution_verified", "worker_invoked", "testing_real_invoked",
             "handoff_allowed", "write_allowed", "dispatch_allowed"}


class EX5CV3Blocked(ValueError):
    pass


def block(reason: str):
    raise EX5CV3Blocked(reason)


def require(cond, reason):
    if not cond:
        block(reason)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def oid(kind: str, raw: bytes) -> str:
    return hashlib.sha1((kind + " " + str(len(raw)) + "\0").encode() + raw).hexdigest()


def decode(x):
    require(isinstance(x, str), "V3_INVALID_BASE64_TYPE")
    try:
        return base64.b64decode(x, validate=True)
    except (ValueError, base64.binascii.Error):
        block("V3_INVALID_BASE64")


def flags_false(x):
    if isinstance(x, dict):
        for key, v in x.items():
            if key in AUTH_KEYS and v is not False:
                block("V3_AUTHORITY_INJECTION_BLOCK")
            flags_false(v)
    elif isinstance(x, list):
        for v in x:
            flags_false(v)


def check_record(record, label):
    require(isinstance(record, dict) and
            set(record) == {"base64", "bytes", "sha256"},
            "V3_" + label + "_RECORD_SHAPE_BLOCK")
    raw = decode(record["base64"])
    require(len(raw) == record["bytes"] and sha(raw) == record["sha256"],
            "V3_" + label + "_BYTES_SHA_BLOCK")
    return raw


def check_execution(cmd: dict, *, name: str, expected_code=None):
    require(isinstance(cmd.get("argv"), list) and bool(cmd["argv"]) and
            type(cmd.get("exit_code")) is int, "V3_" + name + "_COMMAND_BLOCK")
    check_record(cmd["stdout"], name + "_STDOUT")
    check_record(cmd["stderr"], name + "_STDERR")
    if expected_code is not None:
        require(cmd["exit_code"] == expected_code,
                "V3_" + name + "_EXIT_BLOCK")


def git_subtree(rows: list[dict]) -> str:
    require(isinstance(rows, list) and len(rows) >= 18,
            "V3_GIT_BLOB_INVENTORY_BLOCK")
    root = {}
    names = set()
    for item in rows:
        path = item["path"]
        require(isinstance(path, str) and path.startswith("apps/time-service/") and
                ".." not in path.split("/") and path not in names and
                item["mode"] == "100644", "V3_GIT_BLOB_PATH_BLOCK")
        names.add(path)
        raw = decode(item["content_base64"])
        require(len(raw) == item["bytes"] and oid("blob", raw) == item["oid"],
                "V3_GIT_BLOB_OID_BLOCK")
        current = root
        parts = path.removeprefix("apps/time-service/").split("/")
        for part in parts[:-1]:
            current = current.setdefault(part, {})
        require(parts[-1] not in current, "V3_DUPLICATE_GIT_PATH_BLOCK")
        current[parts[-1]] = ("100644", item["oid"])

    def tree(node):
        entries = []
        for name, entry in node.items():
            mode, x = ("40000", tree(entry)) if isinstance(entry, dict) else entry
            entries.append((name, mode, x))
        entries.sort(key=lambda x: (x[0] + ("/" if x[1] == "40000" else "")).encode())
        raw = b"".join(mode.encode() + b" " + name.encode() + b"\0" +
                       bytes.fromhex(x) for name, mode, x in entries)
        return oid("tree", raw)
    return tree(root)


def class_objects(ce: dict):
    before, after = {}, {}
    for key, output in (("baseline_class_objects", before),
                        ("candidate_class_objects", after)):
        rows = ce[key]
        require(isinstance(rows, list) and bool(rows), "V3_CLASSES_MISSING")
        for row in rows:
            path = row["path"]
            require(isinstance(path, str) and path.endswith(".class") and
                    ".." not in path.split("/") and path not in output,
                    "V3_CLASS_PATH_BLOCK")
            raw = decode(row["content_base64"])
            require(sha(raw) == row["sha256"] and len(raw) == row["bytes"],
                    "V3_CLASS_BYTE_SHA_BLOCK")
            output[path] = sha(raw)
    require(before == after == ce["baseline"] == ce["candidate"] and
            len(before) == ce["class_count"] and ce["identical"] is True and
            ce["javac_flags"] == ["--release", "21", "-g:none"],
            "V3_JAVAC_G_NONE_CLASS_EQUIVALENCE_BLOCK")
    return before


def load_v3(path: Path, sha256_fixed: str) -> dict:
    require(bool(re.fullmatch(r"[0-9a-f]{64}", sha256_fixed or "")),
            "V3_SHA_NOT_PINNED_BLOCK")
    require(path.is_file() and not path.is_symlink(), "V3_FIXTURE_NOT_FOUND_BLOCK")
    raw = path.read_bytes()
    require(sha(raw) == sha256_fixed, "V3_BUNDLE_BYTE_TAMPER_BLOCK")
    b = json.loads(raw)
    require(b.get("schema_version") == "LF_EX5C_REAL_EVIDENCE_BUNDLE_V3" and
            b.get("evidence_kind") == "REAL_SANDBOX_UNAUTHENTICATED" and
            b.get("lineage_reason") == "FORMAT_REMEDIATION" and
            b.get("iteration") == "N_PLUS_1" and
            b.get("v1_bundle_sha256") == V1_SHA and
            b.get("v2_bundle_sha256") == V2_SHA and
            b.get("formatter_version") == "1.30.0" and
            b.get("formatter_mode") == "--aosp" and
            b.get("formatter_sha256") == FORMATTER_SHA,
            "V3_N_N1_LINEAGE_OR_FORMATTER_BLOCK")
    flags_false(b)
    g = b["git"]
    require(g.get("commit") == EXPECTED_COMMIT,
            "V3_UNEXPECTED_FINAL_N1_COMMIT_BLOCK")
    actual_commit = decode(g["raw_commit_base64"])
    require(oid("commit", actual_commit) == g["commit"] and
            sha(actual_commit) == g["raw_commit_sha256"] and
            g["commit"] != N and g["base_commit"] == N and
            g["base_subtree"] == "4ba97b68310e913795d7ae1ac35d5912e2fe6551",
            "V3_N1_RAW_COMMIT_OID_BLOCK")
    lines = actual_commit.decode("utf-8", errors="replace").splitlines()
    require("tree " + g["tree"] in lines and
            [x[7:] for x in lines if x.startswith("parent ")] == g["parents"],
            "V3_COMMIT_TREE_OR_PARENTS_BLOCK")
    require(git_subtree(g["files"]) == g["subtree"],
            "V3_REBUILT_SUBTREE_BLOCK")
    patch = b["diff"]
    rawdiff = decode(patch["content_base64"])
    require(sha(rawdiff) == patch["sha256"] and
            len(rawdiff) == patch["bytes"] and
            patch["base_commit"] == N and
            patch["candidate_commit"] == g["commit"] and
            bool(rawdiff), "V3_N1_DIFF_INTEGRITY_BLOCK")
    require(bool(b["changed_java_paths"]) and all(
        path.startswith("apps/time-service/src/main/java/") and path.endswith(".java")
        for path in b["changed_java_paths"]), "V3_CHANGED_FILES_SCOPE_BLOCK")
    class_objects(b["class_equivalence"])
    for key in ("baseline_compile_receipt", "candidate_compile_receipt"):
        compilation = b["class_equivalence"][key]
        check_execution(compilation, name=key.upper(), expected_code=0)
        require("-g:none" in compilation["argv"] and
                "--release" in compilation["argv"] and
                "21" in compilation["argv"], "V3_CLASS_COMPILE_ARGV_BLOCK")
    exe = b["execution"]
    check_execution(exe["baseline_format_check"], name="N_AOSP_FORMAT")
    check_execution(exe["candidate_format_check"], name="N1_AOSP_FORMAT",
                    expected_code=0)
    require(not exe["candidate_format_findings"],
            "V3_N1_FORMAT_FINDINGS_BLOCK")
    check_execution(exe["maven_verify"], name="MAVEN_VERIFY",
                    expected_code=0)
    for name in ("baseline_format_check", "candidate_format_check"):
        require("--aosp" in exe[name]["argv"] and
                "--set-exit-if-changed" in exe[name]["argv"],
                "V3_AOSP_ARGV_BLOCK")
    steps = exe["smoke"]["steps"]
    require([x["status"] for x in steps] == [200, 201, 200, 204, 404],
            "V3_SMOKE_SEQUENCE_STATUS_BLOCK")
    for step in steps:
        rawbody = decode(step["body_base64"])
        require(sha(rawbody) == step["body_sha256"] and
                len(rawbody) == step["body_bytes"], "V3_SMOKE_BODY_BLOCK")
    for key in ("stdout", "stderr"):
        check_record(exe["smoke"][key], "SMOKE_" + key.upper())
    return b
