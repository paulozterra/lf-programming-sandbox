"""Map pinned EX5C v2 Java checks to the *existing* PG06 C4 / PG08 C2 input shapes.

V2 JSON is an additive, separate fixture. Every stdout/stderr, source blob
and parsed finding is checked before projecting source-only observations.
Do not call the original producers without their prior (non-authoritative)
PG05/PG06 and PG08 C1 lineage. Never authenticate execution or grant authority.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

BASE = "28de535acd4a76be038013cc6241c59a08102155"
HEAD = "e76b213cb2f367f787e0eba3bf8ff74136edd883"
V1_SHA = "436bc771ccd04b5eeb407102f7c55a3338bacf43f8f292773f293aa615a8da3b"
GJF_SHA = "f2239a8a234a240a54fdff7809d4b3e66702c21f590c77a0b6cf7b20c829e95a"
PATCH_SHA = "bfba0329bcac92dbde06a1319a16acd535acd718f224df6121dae3c70fe307c6"
REPO = "paulozterra/lf-programming-sandbox"


class V2EvidenceBlocked(ValueError):
    pass


def block(reason):
    raise V2EvidenceBlocked(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def validate_stream(row, *, label):
    if not isinstance(row, dict) or set(row) != {"base64", "bytes", "sha256"}:
        block("V2_" + label + "_SHAPE_BLOCK")
    try:
        raw = base64.b64decode(row["base64"], validate=True)
    except (ValueError, TypeError):
        block("V2_" + label + "_BASE64_BLOCK")
    if sha(raw) != row["sha256"] or len(raw) != row["bytes"]:
        block("V2_" + label + "_DIGEST_BLOCK")
    return raw


def command(check, *, label):
    if not isinstance(check, dict) or not isinstance(check.get("argv"), list):
        block("V2_" + label + "_COMMAND_BLOCK")
    for stream in ("stdout", "stderr"):
        validate_stream(check.get(stream), label=label + "_" + stream.upper())
    if type(check.get("exit_code")) is not int or check["exit_code"] < 0:
        block("V2_" + label + "_EXIT_INVALID_BLOCK")


def oid(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def load_v2(path: Path, fixed_sha256: str) -> dict:
    if not fixed_sha256 or len(fixed_sha256) != 64 or not path.is_file() or path.is_symlink():
        block("V2_FIXTURE_SHA_OR_PATH_NOT_PINNED_BLOCK")
    raw = path.read_bytes()
    if sha(raw) != fixed_sha256:
        block("V2_FIXTURE_SHA_CHANGED_BLOCK")
    b = json.loads(raw)
    if (b.get("schema_version") != "LF_EX5C_REAL_EVIDENCE_BUNDLE_V2" or
        b.get("evidence_kind") != "REAL_SANDBOX_UNAUTHENTICATED" or
        b.get("base_commit") != BASE or b.get("candidate_commit") != HEAD or
        b.get("v1_bundle_sha256") != V1_SHA or b.get("diff_sha256") != PATCH_SHA or
        b.get("formatter_version") != "1.30.0" or b.get("formatter_sha256") != GJF_SHA or
        any(b.get(flag) is not False for flag in
            ("production_authority", "tool_execution_verified",
             "receipt_authenticated", "worker_invoked"))):
        block("V2_SOURCE_IDENTITY_OR_AUTHORITY_BLOCK")
    snapshots = b.get("snapshots")
    if (not isinstance(snapshots, list) or len(snapshots) != 2 or
        [x.get("label") for x in snapshots] != ["baseline", "candidate"] or
        [x.get("commit") for x in snapshots] != [BASE, HEAD]):
        block("V2_SNAPSHOT_CHAIN_BLOCK")
    for item in snapshots:
        if item.get("authority_authenticated") is not False or item.get("candidate_source") != "EXACT_GIT_CHECKOUT":
            block("V2_NESTED_AUTHORITY_INJECTION_BLOCK")
        fmt, lint = item["formatter"], item["javac"]
        if fmt["version"] != "1.30.0" or fmt["jar_sha256"] != GJF_SHA:
            block("V2_FORMATTER_TOOL_PIN_BLOCK")
        command(fmt["execution"], label="FORMAT")
        command(lint["execution"], label="JAVAC")
        command(lint["version_output"], label="JAVAC_VERSION")
        command(lint["classpath_resolver"], label="MAVEN_CLASSPATH")
        if (fmt["execution"]["argv"][:5] != ["java", "-jar",
            fmt["execution"]["argv"][2], "--dry-run", "--set-exit-if-changed"] or
            "--release" not in lint["execution"]["argv"] or
            "-Xlint:all" not in lint["execution"]["argv"]):
            block("V2_TOOL_ARGV_BLOCK")
        if fmt["execution"]["exit_code"] not in (0, 1) or (
            lint["reported_outcome"] != ("PASS" if lint["execution"]["exit_code"] == 0 else "FAIL")):
            block("V2_TOOL_RESULT_EXIT_CONTRADICTION_BLOCK")
        rows = item["files"]
        if not isinstance(rows, list) or len(rows) < 3:
            block("V2_SOURCE_FILES_MISSING_BLOCK")
        for entry in rows:
            if not entry["path"].startswith("apps/time-service/src/main/java/") or ".." in entry["path"]:
                block("V2_SOURCE_SCOPE_BLOCK")
            source = validate_stream({"base64": entry["content_base64"],
                                      "sha256": entry["blob_sha256"],
                                      "bytes": entry["bytes"]}, label="JAVA_BLOB")
            if oid(source) != entry["git_blob_oid"]:
                block("V2_GIT_BLOB_OID_BLOCK")
        known = {e["path"] for e in rows}
        for f in fmt["findings"]:
            if f["path"] not in known or f["line_start"] < 1:
                block("V2_FORMAT_FINDING_SOURCE_BLOCK")
        for f in lint["findings"]:
            if f["path"] not in known or f["line"] < 1:
                block("V2_JAVAC_FINDING_SOURCE_BLOCK")
    return b


def stable_violation(kind, path, line, source):
    return "EX5C-" + sha(canonical({
        "rule": kind, "path": path, "line": line, "source": source
    }))[:24]


def violation_rows(snapshot: dict, *, candidate: bool) -> list[dict]:
    changed = {
        "apps/time-service/src/main/java/lf/sandbox/time/reminder/ReminderRepository.java",
        "apps/time-service/src/main/java/lf/sandbox/time/reminder/InMemoryReminderRepository.java",
        "apps/time-service/src/main/java/lf/sandbox/time/reminder/ReminderController.java"
    }
    rows = []
    for f in snapshot["formatter"]["findings"]:
        p, line = f["path"], f["line_start"]
        rows.append({
            "kind": "FORMAT",
            "violation_ref": stable_violation("GOOGLE_JAVA_FORMAT", p, line,
                                              f["old_sha256"]),
            "severity": "BLOCK", "rule_id": "GOOGLE_JAVA_FORMAT",
            "path": p, "line": line,
            "scope": "DIFF" if candidate and p in changed else "REPOSITORY"
        })
    for f in snapshot["javac"]["findings"]:
        p, line = f["path"], f["line"]
        rows.append({
            "kind": "LINT",
            "violation_ref": stable_violation("JAVAC_" + f["kind"], p, line,
                                              f["message"]),
            "severity": "BLOCK" if f["kind"] == "error" else "WARN",
            "rule_id": "JAVAC_XLINT_ALL", "path": p, "line": line,
            "scope": "DIFF" if candidate and p in changed else "REPOSITORY"
        })
    return rows


def to_pg06_c4_baseline(v2: dict, *, solution_id="EX5C") -> dict:
    """Exact original PG06C4 baseline_observations input; original source required."""
    snap = v2["snapshots"][0]
    commands = []
    format_check = snap["formatter"]["execution"]
    compiler = snap["javac"]["execution"]
    checks = (
        ("BUILD", compiler, [f for f in violation_rows(snap, candidate=False)
                             if f["kind"] == "LINT"]),
        ("LINT", format_check, [f for f in violation_rows(snap, candidate=False)
                              if f["kind"] == "FORMAT"])
    )
    for kind, observed, findings in checks:
        commands.append({
            "command_id": "EX5C-BASE-" + kind,
            "solution_id": solution_id, "kind": kind,
            "command_ref": "evidence:ex5c:v2:baseline:" + kind,
            "command_sha256": sha(canonical(observed["argv"])),
            "result": "PASS" if observed["exit_code"] == 0 else "FAIL",
            "exit_code": observed["exit_code"],
            "stdout_sha256": observed["stdout"]["sha256"],
            "stderr_sha256": observed["stderr"]["sha256"],
            "violation_refs": sorted({f["violation_ref"] for f in findings})
                  if observed["exit_code"] != 0 else [],
            "execution_receipt_ref": "sandbox:ex5c:v2:baseline:" + kind
        })
    return {
        "schema_version": "PG06_UNCHANGED_TARGET_BASELINE_OBSERVATION_CANDIDATE_V1",
        "target_repo": REPO, "base_head_sha": BASE,
        "observation_ref": "sandbox:ex5c:v2:baseline",
        "execution_environment_ref": "local-github-actions-jdk21",
        "unchanged_target_claim": True,
        "command_results": commands
    }


def to_pg08_c2_candidate(v2: dict, *, solution_id="EX5C") -> list[dict]:
    snap = v2["snapshots"][1]
    findings = violation_rows(snap, candidate=True)
    checks = []
    for kind in ("FORMAT", "LINT"):
        block_ = snap["formatter"] if kind == "FORMAT" else snap["javac"]
        observed = block_["execution"]
        seen = [f for f in findings if f["kind"] == kind]
        checks.append({
            "kind": kind, "command_id": "EX5C-CANDIDATE-" + kind,
            "command_ref": "evidence:ex5c:v2:candidate:" + kind,
            "tool_name": "google-java-format" if kind == "FORMAT" else "javac",
            "tool_version": "1.30.0" if kind == "FORMAT" else "JDK21",
            "config_sha256": GJF_SHA if kind == "FORMAT" else sha(
                canonical(["javac", "--release", "21", "-Xlint:all"])),
            "execution_receipt_ref": "sandbox:ex5c:v2:candidate:" + kind,
            "stdout_sha256": observed["stdout"]["sha256"],
            "stderr_sha256": observed["stderr"]["sha256"],
            "result": "PASS" if observed["exit_code"] == 0 else "FAIL",
            "exit_code": observed["exit_code"],
            "findings": [{key: f[key] for key in
                         ("violation_ref", "severity", "rule_id", "path", "line", "scope")}
                         for f in seen]
        })
    return [{
        "solution_id": solution_id,
        "executor_mode": "WORKER_API",
        "candidate_head_sha": HEAD,
        "diff_sha256": PATCH_SHA,
        "target_repo": REPO,
        "base_head_sha": BASE,
        "checks": checks
    }]


V2_FIXTURE_SHA256 = "0988de2e39f5139596d05c3cbfcbe8c8998c753cdb009414e5b38da65172217b"
V2_FIXTURE_PATH = (Path(__file__).resolve().parents[1] /
                   "fixtures/lf-evidence-bundle-v2.json")


def source_envelope(schema: str, **fields) -> dict:
    """Projection only: not an actual PG05/PG06 C1-C3 producer or authenticated source."""
    obj = {"schema_version": schema, "status": "CANDIDATE_NOT_ADMITTED",
           "production_authority": False, "handoff_allowed": False, **fields}
    obj["candidate_sha256"] = sha(canonical(obj))
    return obj


def run_real_pg06_c4_pg08_c2(*, v1: dict, v2: dict) -> dict:
    """Import ORIGINAL PG06 C4 and PG08 C2; do not modify producers.

    PG05 and PG06 C1-C3 are projected source-only envelopes, not independently
    executed producer results. All measurable format/compile bytes originate
    from the SHA-pinned V2 and the build/source identity from the pinned V1.
    Thus this is an evidence replay, NOT a complete LF production lineage.
    """
    import importlib.util
    import sys
    stage_root = Path(__file__).resolve().parents[2]
    tools_dir = Path(__file__).resolve().parent
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))
    from pg07_real_worker_evidence_adapter_v1 import run_real_pg08_c1

    def load_producer(folder: str, name: str, symbol: str):
        src = stage_root / folder / "tools" / (name + ".py")
        if not src.is_file():
            block("V2_REAL_PRODUCER_MISSING_BLOCK")
        spec = importlib.util.spec_from_file_location("ex5c_" + name, src)
        if spec is None or spec.loader is None:
            block("V2_REAL_PRODUCER_IMPORT_BLOCK")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return getattr(mod, symbol)

    # Fail closed even for direct programmatic calls that bypass load_v2().
    # Both upstream bundles use canonical, sorted, ensure_ascii JSON + LF.
    if (sha(canonical(v1) + b"\n") != V1_SHA or
        sha(canonical(v2) + b"\n") != V2_FIXTURE_SHA256):
        block("V2_DIRECT_PRODUCER_INPUT_REHASH_OR_BYTES_BLOCK")
    # Require the exact frozen V1/V2 historical Git source pair and no authority.
    if (v1["git"]["commit"] != HEAD or v1["git"]["base_commit"] != BASE or
        v2["candidate_commit"] != HEAD or v2["base_commit"] != BASE or
        v2["v1_bundle_sha256"] != V1_SHA):
        block("V2_EX5C_CROSS_BUNDLE_BINDING_BLOCK")
    result_c1 = run_real_pg08_c1(v1)["pg08_c1"]
    pg05 = source_envelope("PG05_TO_PG06_EXIT_CANDIDATE_V1",
        target_binding={"repo_full_name": REPO, "base_head_sha": BASE},
        solutions=[{"solution_id": "EX5C"}],
        source_ref="sha256:" + V1_SHA)
    pg06_1 = source_envelope("PG06_C1_CURRENTNESS_REUSE_CANDIDATE_V1",
        source_pg05_exit_sha256=pg05["candidate_sha256"],
        execution_allowed=False)
    pg06_2 = source_envelope("PG06_C2_TOOLCHAIN_PREFLIGHT_CANDIDATE_V1",
        source_pg05_exit_sha256=pg05["candidate_sha256"],
        source_pg06_c1_sha256=pg06_1["candidate_sha256"],
        pg06_ready=False)
    pg06_3 = source_envelope("PG06_C3_REVERSIBILITY_PLAN_CANDIDATE_V1",
        source_pg05_exit_sha256=pg05["candidate_sha256"],
        source_pg06_c1_sha256=pg06_1["candidate_sha256"],
        source_pg06_c2_sha256=pg06_2["candidate_sha256"],
        write_allowed=False, pg06_admitted=False)
    c4 = load_producer("pg06_preflight_candidate",
        "pg06_c4_baseline_capture_candidate_v1", "prepare_pg06_c4")(
            pg05_exit=pg05, pg06_c1=pg06_1, pg06_c2=pg06_2, pg06_c3=pg06_3,
            baseline_observations=to_pg06_c4_baseline(v2))
    c2 = load_producer("pg08_build_candidate",
        "pg08_c2_format_lint_delta_candidate_v1", "prepare_pg08_c2")(
            pg06_c4=c4, pg08_c1=result_c1,
            lint_observations=to_pg08_c2_candidate(v2))
    if (c4.get("production_authority") is not False or
        c2.get("production_authority") is not False or
        c2.get("source_pg06_c4_sha256") != c4["candidate_sha256"] or
        c2.get("source_pg08_c1_sha256") != result_c1["candidate_sha256"]):
        block("V2_ORIGINAL_PRODUCER_AUTHORITY_OR_LINEAGE_BLOCK")
    if c2["solutions"][0]["reported_diagnostic"] != "REPORTED_NEW_BLOCKERS":
        block("V2_REAL_FORMAT_NEW_BLOCKERS_DIAGNOSTIC_DRIFT")
    return {
        "pg05_pg06_c1_c3_provenance": "ADAPTER_PROJECTED_SOURCE_ONLY_UNAUTHENTICATED",
        "pg06_c4": c4, "pg08_c1": result_c1, "pg08_c2": c2,
        "v1_sha256": V1_SHA, "v2_sha256": V2_FIXTURE_SHA256,
        "evidence_kind": "REAL_SANDBOX_UNAUTHENTICATED",
        "production_authority": False,
        "next_gate": "PG08_C2_REPORTED_NEW_BLOCKERS_REQUIRES_GOVERNED_REVIEW"
    }
