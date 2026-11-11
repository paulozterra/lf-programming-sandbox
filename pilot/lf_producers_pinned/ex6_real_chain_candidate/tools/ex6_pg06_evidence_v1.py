"""EX6-only PG06 C2 + C4 evidence from immutable public source and CI logs.

No simulated tool invocation, no baseline lint/format PASS, no A7 synthesis.
The original v1 producers remain unchanged. All outputs are candidate-only.
"""
from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from pathlib import Path

EVIDENCE = Path(__file__).resolve().parents[1] / "evidence"
POM_BLOB = "dab45a1d6580ed53ebe67b341312ef588cb80131"
NATIVE_LOG_BLOB = "8c7254cd16c45ee777bbf219fdc161155ed24743"
BASELINE_LOG_BLOB = "4913a5ffdf93df35dce52f1cb518e80710b6daaf"
TIME_SERVICE_TREE_SHA = "2c199d6c49b76ea8a23e15149425ece0f29e1410"
BASE_SHA = "53ab6b1a85da95f3e2a38d7f3298af731c6698ab"
BASELINE_PR_HEAD = "3634fdea8ae63b0f5e48fc4925e7f9dfd0d74f62"
BASELINE_CHECKOUT_SHA = "6e5a0a444edaa6fc0ec66d59883c4c83d218717f"
NATIVE_RUN = 42674262914
BASELINE_RUN = 42664733176
BASELINE_JOB = 129325278303
NATIVE_JOB = 129351701663

class EX6ToolchainEvidenceBlocked(ValueError):
    pass

def _block(reason):
    raise EX6ToolchainEvidenceBlocked(reason)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def _git_oid(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()

def _read(name, sha):
    path = EVIDENCE / name
    if not path.is_file() or path.is_symlink():
        _block("EX6_PG06_PUBLIC_SOURCE_MISSING:" + name)
    data = path.read_bytes()
    if _git_oid(data) != sha:
        _block("EX6_PG06_PUBLIC_SOURCE_GIT_BLOB_DRIFT:" + name)
    return data

def source_evidence():
    pom_raw = _read("ex6_base_pom.xml", POM_BLOB)
    native_raw = _read("ex6_native_java21_log_excerpt.txt", NATIVE_LOG_BLOB)
    baseline_raw = _read("ex6_baseline_ci_log_excerpt.txt", BASELINE_LOG_BLOB)
    root = ET.fromstring(pom_raw)
    ns = {"m": "http://maven.apache.org/POM/4.0.0"}
    java = root.findtext("./m:properties/m:java.version", namespaces=ns)
    spring = root.findtext("./m:parent/m:version", namespaces=ns)
    parent = root.findtext("./m:parent/m:artifactId", namespaces=ns)
    if parent != "spring-boot-starter-parent" or java != "21" or spring != "4.1.1":
        _block("EX6_PG06_POM_VERSION_DRIFT")
    n = native_raw.decode("utf-8")
    b = baseline_raw.decode("utf-8")
    if ("java-version: " + java not in n or
        "Resolved Java 21.0.13+9 from tool-cache" not in n or
        "Java_Temurin-Hotspot_jdk/21.0.13-9" not in n or
        "EX6_ISOLATED_JAVA21_AND_MAVEN_PASS" not in n):
        _block("EX6_PG06_NATIVE_JAVA21_LOG_MISSING")
    if ("java-version: " + java not in b or
        "mvn -B -q -f apps/time-service/pom.xml test" not in b or
        "TimeServiceContextTest using Java 21.0.13" not in b):
        _block("EX6_PG06_BASELINE_BUILD_LOG_MISSING")
    return {
        "pom_sha256": digest(pom_raw),
        "native_log_excerpt_sha256": digest(native_raw),
        "baseline_log_excerpt_sha256": digest(baseline_raw),
        "pom_git_blob_sha": POM_BLOB,
        "native_log_git_blob_sha": NATIVE_LOG_BLOB,
        "baseline_log_git_blob_sha": BASELINE_LOG_BLOB,
        "java_version": java, "spring_boot_version": spring,
        "temurin_version": "21.0.13+9",
        "base_tree_sha": TIME_SERVICE_TREE_SHA,
        "pr_head_tree_sha": TIME_SERVICE_TREE_SHA,
        "pr_merge_tree_sha": TIME_SERVICE_TREE_SHA,
        "pr_head_sha": BASELINE_PR_HEAD,
        "pr_merge_checkout_sha": BASELINE_CHECKOUT_SHA,
        "baseline_check_conclusion": "SUCCESS",
        "baseline_command": "mvn -B -q -f apps/time-service/pom.xml test",
        "baseline_lint": "pending-execution",
        "pg01_status": "FIXTURE_UNATTESTED",
    }

def c2_inputs(pg05_exit):
    evidence = source_evidence()
    target = pg05_exit["target_binding"]
    if target["base_head_sha"] != BASE_SHA:
        _block("EX6_PG06_BASE_HEAD_DRIFT")
    sol_ids = [s["solution_id"] for s in pg05_exit["solutions"]]
    if not sol_ids:
        _block("EX6_PG06_SOLUTIONS_MISSING")
    ref = "ex6://sandbox/blob/" + BASE_SHA + "/apps/time-service/pom.xml"
    native = "ex6://sandbox/actions/runs/" + str(NATIVE_RUN)
    catalog = {
        "schema_version": "PG06_TOOLCHAIN_CATALOG_SELECTION_CANDIDATE_V1",
        "catalog_ref": ref,
        "catalog_sha256": evidence["pom_sha256"],
        "profile_ref": "stack://java21-maven-spring-boot",
        "target_repo": target["repo_full_name"],
        "target_base_head_sha": BASE_SHA,
        "requirements": [{
            "tool_id": "java",
            "component": "backend",
            "version_exact": evidence["java_version"],
            "source_ref": ref + "#java.version",
            "applies_to_solution_ids": sol_ids,
        }],
    }
    observation = {
        "schema_version": "PG06_TOOLCHAIN_ENVIRONMENT_OBSERVATION_CANDIDATE_V1",
        "environment_ref": native,
        "observed_target_repo": target["repo_full_name"],
        "observed_base_head_sha": BASE_SHA,
        "observations": [{
            "tool_id": "java",
            "reported_version": evidence["java_version"],
            "availability": "AVAILABLE",
            "evidence_ref": native + "/jobs/" + str(NATIVE_JOB)
                + "#EX6_ISOLATED_JAVA21_AND_MAVEN_PASS#sha256="
                + evidence["native_log_excerpt_sha256"],
        }],
    }
    return catalog, observation

def c4_partial_baseline(pg05_exit):
    """Real CI proves base BUILD/test only; never fabricate lint/format."""
    facts = source_evidence()
    target = pg05_exit["target_binding"]
    if target["base_head_sha"] != BASE_SHA:
        _block("EX6_PG06_C4_TARGET_DRIFT")
    ref = "ex6://sandbox/actions/runs/" + str(BASELINE_RUN)
    return {
        "schema_version": "EX6_PG06_BASELINE_PARTIAL_V1",
        "target_repo": target["repo_full_name"],
        "base_head_sha": BASE_SHA,
        "observation_ref": ref + "#time-service-identical-tree/" + TIME_SERVICE_TREE_SHA,
        "execution_environment_ref": ref + "/jobs/" + str(BASELINE_JOB),
        "unchanged_target_claim": True,
        # The full stdout/stderr stream SHA was not published separately.
        # A partial log excerpt hash is NOT equivalent to full stdout/stderr SHA.
        # No command_results are asserted, so C4 correctly cannot PASS.
        "command_results": [],
        "proven_build": {
            "check": "backend (Maven verify)", "conclusion": "SUCCESS",
            "command": facts["baseline_command"],
            "command_ref": ref + "/jobs/" + str(BASELINE_JOB),
            "log_excerpt_sha256": facts["baseline_log_excerpt_sha256"],
            "tree_sha": TIME_SERVICE_TREE_SHA,
        },
        "lint_status": "pending-execution",
    }
