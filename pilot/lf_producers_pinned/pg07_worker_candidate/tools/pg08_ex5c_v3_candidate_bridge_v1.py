"""Project genuine v3 N+1 bytes into ORIGINAL PG06 C4 and PG08 C1/C2.

Nothing is admitted: PG05/PG06 C1-C3 and PG07 C6 are explicitly projected
SOURCE_ONLY_UNAUTHENTICATED references, not synthetic tool outcomes or claims
that LF executed the Worker again. Original stages run only after the new
SHA-fixed real v3 fixture exists. No producer modifications, no PG14 ACCEPT.
"""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
from pathlib import Path

from pg07_ex5c_format_remediation_v3_adapter_v1 import (
    V1_SHA, V2_SHA, FORMATTER_SHA, N,
    EX5CV3Blocked, require, sha, decode, load_v3,
)

REPO = "paulozterra/lf-programming-sandbox"
ROOT = Path(__file__).resolve().parents[2]


def canonical(v):
    return json.dumps(v, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode()


def digest(v):
    return sha(canonical(v))


def source(schema, **kwargs):
    item = {"schema_version": schema, "status": "CANDIDATE_NOT_ADMITTED",
            "production_authority": False, "handoff_allowed": False, **kwargs}
    item["candidate_sha256"] = digest(item)
    return item


def producer(stage, module, fn):
    file = ROOT / stage / "tools" / (module + ".py")
    require(file.is_file(), "V3_REAL_PRODUCER_NOT_FOUND")
    spec = importlib.util.spec_from_file_location(module + "_ex5c_n1", file)
    require(spec is not None and spec.loader is not None,
            "V3_PRODUCER_IMPORT_BLOCK")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, fn)


def ref_format(f):
    return "EX5C-AOSP-" + sha(canonical({
        "rule": "GOOGLE_JAVA_FORMAT_AOSP_1_30_0",
        "path": f["path"], "line": f["line_start"],
        "old_sha256": f["old_sha256"]
    }))[:24]


def source_hunks(b):
    return b["diff"]["sha256"]


def projected_pg07_c6(b):
    h = b["git"]["commit"]
    candidate = {
        "solution_id": "EX5C_FORMAT_N1",
        "candidate_head_sha_reported": h,
        "diff_sha256_reported": source_hunks(b),
        "changed_paths_reported": sorted(b["changed_java_paths"]),
        "receipt_authenticated": False, "worker_invoked": False,
        "production_authority": False,
    }
    return source("PG07_C6_BATCH_EVIDENCE_MANIFEST_CANDIDATE_V1",
                  target_repo=REPO, base_head_sha=N, batches=[candidate],
                  source_adapter_ref="EX5C_V3_N1_AOSP_SOURCE_ONLY",
                  evidence_kind="REAL_SANDBOX_UNAUTHENTICATED",
                  worker_invoked=False, receipt_sealed=False,
                  pg12_admitted=False, dispatch_allowed=False,
                  write_allowed=False)


def projected_pg08_c1(b):
    stage = "pg08_build_candidate"
    fn = producer(stage, "pg08_c1_build_compilation_candidate_v1",
                  "prepare_pg08_c1")
    upstream = projected_pg07_c6(b)
    build = b["execution"]["maven_verify"]
    by_path = {r["path"]: r for r in b["git"]["files"]}
    pom = by_path["apps/time-service/pom.xml"]
    pom_sha = sha(decode(pom["content_base64"]))
    observation = [{
        "solution_id": "EX5C_FORMAT_N1", "executor_mode": "WORKER_API",
        "executor_result_ref": "sandbox:ex5c:v3:format-remediation-no-model",
        "candidate_head_sha": b["git"]["commit"],
        "diff_sha256": b["diff"]["sha256"],
        "target_repo": REPO, "base_head_sha": N,
        "commands": [{
            "command_id": "N1-MAVEN-VERIFY", "command_ref": "sandbox:v3:maven",
            "tool_name": "mvn", "tool_version": "Maven-JDK21",
            "config_sha256": pom_sha,
            "execution_receipt_ref": "sandbox:v3:maven",
            "stdout_sha256": build["stdout"]["sha256"],
            "stderr_sha256": build["stderr"]["sha256"],
            "result": "PASS" if build["exit_code"] == 0 else "FAIL",
            "exit_code": build["exit_code"]
        }]
    }]
    return fn(pg07_c6=upstream, build_observations=observation)


def projected_pg06_c4(b):
    pg05 = source("PG05_TO_PG06_EXIT_CANDIDATE_V1",
                  target_binding={"repo_full_name": REPO, "base_head_sha": N},
                  solutions=[{"solution_id": "EX5C_FORMAT_N1"}],
                  run_ref="sandbox:v3:N1")
    c1 = source("PG06_C1_CURRENTNESS_REUSE_CANDIDATE_V1",
                source_pg05_exit_sha256=pg05["candidate_sha256"],
                execution_allowed=False)
    c2 = source("PG06_C2_TOOLCHAIN_PREFLIGHT_CANDIDATE_V1",
                source_pg05_exit_sha256=pg05["candidate_sha256"],
                source_pg06_c1_sha256=c1["candidate_sha256"], pg06_ready=False)
    c3 = source("PG06_C3_REVERSIBILITY_PLAN_CANDIDATE_V1",
                source_pg05_exit_sha256=pg05["candidate_sha256"],
                source_pg06_c1_sha256=c1["candidate_sha256"],
                source_pg06_c2_sha256=c2["candidate_sha256"],
                write_allowed=False, pg06_admitted=False)
    base = b["execution"]["baseline_format_check"]
    build = b["class_equivalence"]["baseline_compile_receipt"]
    violations = sorted({ref_format(f) for f in
                         b["execution"]["baseline_format_findings"]})
    checks = []
    for kind, r, found in (("BUILD", build, []),
                           ("LINT", base, violations)):
        checks.append({
            "command_id": "N1-BASE-" + kind, "solution_id": "EX5C_FORMAT_N1",
            "kind": kind, "command_ref": "sandbox:v3:baseline:" + kind,
            "command_sha256": digest(r["argv"]),
            "result": "PASS" if r["exit_code"] == 0 else "FAIL",
            "exit_code": r["exit_code"],
            "stdout_sha256": r["stdout"]["sha256"],
            "stderr_sha256": r["stderr"]["sha256"],
            "violation_refs": found if r["exit_code"] != 0 else [],
            "execution_receipt_ref": "sandbox:v3:baseline:" + kind
        })
    observations = {
        "schema_version": "PG06_UNCHANGED_TARGET_BASELINE_OBSERVATION_CANDIDATE_V1",
        "target_repo": REPO, "base_head_sha": N,
        "observation_ref": "sandbox:ex5c:v3:N-original-AOSP",
        "execution_environment_ref": "sandbox:actions:v3-JDK21",
        "unchanged_target_claim": True,
        "command_results": checks
    }
    fn = producer("pg06_preflight_candidate",
                  "pg06_c4_baseline_capture_candidate_v1",
                  "prepare_pg06_c4")
    return fn(pg05_exit=pg05, pg06_c1=c1, pg06_c2=c2,
              pg06_c3=c3, baseline_observations=observations)


def projected_pg08_c2(b, *, pg06_c4, pg08_c1):
    checks = []
    for kind, r, names in (
        ("FORMAT", b["execution"]["candidate_format_check"],
         b["execution"]["candidate_format_findings"]),
        ("LINT", b["class_equivalence"]["candidate_compile_receipt"],
         b["class_equivalence"]["candidate_lint_findings"])
    ):
        findings = []
        for f in names:
            if kind == "FORMAT":
                violation = ref_format(f)
                rule = "GOOGLE_JAVA_FORMAT_AOSP_1_30_0"
                line = f["line_start"]
                severity = "BLOCK"
            else:
                rule = "JAVAC_XLINT_ALL"
                line = f["line"]
                severity = "BLOCK" if f["kind"] == "error" else "WARN"
                violation = "EX5C-JAVAC-" + sha(canonical(f))[:24]
            findings.append({
                "violation_ref": violation, "severity": severity,
                "rule_id": rule, "path": f["path"],
                "line": line, "scope": "DIFF"
            })
        checks.append({
            "kind": kind, "command_id": "N1-" + kind,
            "command_ref": "sandbox:v3:candidate:" + kind,
            "tool_name": "google-java-format" if kind == "FORMAT" else "javac",
            "tool_version": "1.30.0 --aosp" if kind == "FORMAT" else "JDK21 -Xlint:all",
            "config_sha256": FORMATTER_SHA if kind == "FORMAT" else
                             digest(["javac", "--release", "21", "-g:none", "-Xlint:all"]),
            "execution_receipt_ref": "sandbox:v3:candidate:" + kind,
            "stdout_sha256": r["stdout"]["sha256"],
            "stderr_sha256": r["stderr"]["sha256"],
            "result": "PASS" if r["exit_code"] == 0 else "FAIL",
            "exit_code": r["exit_code"], "findings": findings,
        })
    observations = [{
        "solution_id": "EX5C_FORMAT_N1", "executor_mode": "WORKER_API",
        "candidate_head_sha": b["git"]["commit"],
        "diff_sha256": b["diff"]["sha256"], "target_repo": REPO,
        "base_head_sha": N, "checks": checks
    }]
    fn = producer("pg08_build_candidate",
                  "pg08_c2_format_lint_delta_candidate_v1",
                  "prepare_pg08_c2")
    return fn(pg06_c4=pg06_c4, pg08_c1=pg08_c1,
              lint_observations=observations)


def run_real_n1_pg06_pg08_c1_c2(path: Path, fixed_sha: str):
    """Stops at earliest real producer; never claims PG08 C3..C8 or PG14."""
    b = load_v3(path, fixed_sha)
    c4 = projected_pg06_c4(b)
    c1 = projected_pg08_c1(b)
    c2 = projected_pg08_c2(b, pg06_c4=c4, pg08_c1=c1)
    require(c1["production_authority"] is False and
            c2["production_authority"] is False and
            c2["source_pg06_c4_sha256"] == c4["candidate_sha256"] and
            c2["source_pg08_c1_sha256"] == c1["candidate_sha256"],
            "V3_PG06_PG08_LINEAGE_OR_AUTHORITY_BLOCK")
    return {"v3_sha256": fixed_sha,
            "pg06_c4": c4, "pg08_c1": c1, "pg08_c2": c2,
            "source_provenance": "ADAPTER_PROJECTED_UNAUTHENTICATED",
            "production_authority": False, "handoff_allowed": False}
