"""Strict EX6 run 42707967927 originals -> LF v1 PG06, PG08 and PG12.

Loads the exact Git-blob-preserved ZIP and verifies archive, member, streams,
commands and snapshot identities. Transforms only into source-only candidate
observations. AOSP exit=1 is a genuine FORMAT FAIL, never a passing receipt.
"""
from __future__ import annotations
import base64
import hashlib
import json
from pathlib import Path
from contextvars import ContextVar
from contextlib import contextmanager
from ex6_n1_receipts_v1 import load as load_exact_receipt, EXPECTED as RECEIPTS

from ex6_build_lint_index_v1 import original_zip_integrity, EX6EvidenceBlocked
from ex6_source_truth_v1 import RUN_REF, SPEC_REF

BUNDLE_REF = "ex6://sandbox/actions/runs/42707967927/artifacts/13715275651"
SNAPSHOT_BASE = "53ab6b1a85da95f3e2a38d7f3298af731c6698ab"
SNAPSHOT_MERGED = "912c4ad9ea71f48edbd1ac58089441f9ed2c3449"
AOSP_RULE = "CHG-0015-AOSP"
_ACTIVE=ContextVar("ex6_receipt_version",default="N")
@contextmanager
def using_receipt(label):
    if label not in RECEIPTS:
        raise EX6EvidenceBlocked("EX6_UNKNOWN_RECEIPT")
    token=_ACTIVE.set(label)
    try:
        yield
    finally:
        _ACTIVE.reset(token)
def active_label():
    return _ACTIVE.get()
def active_ref():
    if active_label()=="N":
        return BUNDLE_REF  # original ref stays byte-for-byte identical for old contracts
    row=RECEIPTS[active_label()]
    return "ex6://sandbox/actions/runs/"+str(row["run"])+"/sha256/"+row["json"]
def active_candidate():
    return RECEIPTS[active_label()]["candidate"]


def sha(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),
        ensure_ascii=True).encode()).hexdigest()

def observed():
    d=load_exact_receipt(active_label())
    if ([s["commit"] for s in d["snapshots"]] !=
         [SNAPSHOT_BASE,active_candidate()] or
        d["formatter_flags"] != ["--aosp","--dry-run","--set-exit-if-changed"]):
        raise EX6EvidenceBlocked("EX6_BUNDLE_SNAPSHOT_OR_AOSP_DRIFT")
    base,cand=(s["commands"] for s in d["snapshots"])
    required=("build","classpath_resolution","format_aosp","javac_lint")
    for name in required:
        for obs in (base,cand):
            v=obs[name]
            if (not isinstance(v.get("argv"),list) or
                type(v.get("exit_code")) is not int):
                raise EX6EvidenceBlocked("EX6_BUNDLE_COMMAND_SHAPE_DRIFT")
            for stream in ("stdout","stderr"):
                value=base64.b64decode(v[stream]["base64"],validate=True)
                if hashlib.sha256(value).hexdigest()!=v[stream]["sha256"]:
                    raise EX6EvidenceBlocked("EX6_BUNDLE_STREAM_BYTES_DRIFT")
    if (base["build"]["exit_code"]!=0 or cand["build"]["exit_code"]!=0
        or base["javac_lint"]["exit_code"]!=0
        or cand["javac_lint"]["exit_code"]!=0
        or base["format_aosp"]["exit_code"]!=0
        or cand["format_aosp"]["exit_code"]!=RECEIPTS[active_label()]["aosp"]
        or cand["visible_ex6"]["exit_code"]!=0):
        raise EX6EvidenceBlocked("EX6_BUNDLE_COMMAND_RESULT_DRIFT")
    stdout=base64.b64decode(cand["format_aosp"]["stdout"]["base64"]).decode("utf-8")
    paths=stdout.splitlines()
    expected={"ReminderStats.java","ReminderStatsService.java","ReminderStatsController.java"}
    if (active_label()=="N" and (len(paths)!=3 or {Path(v).name for v in paths}!=expected)) or (active_label()=="N1" and paths):
        raise EX6EvidenceBlocked("EX6_BUNDLE_AOSP_FINDINGS_DRIFT")
    return d

def command_ref(snapshot, key):
    return active_ref() + "#"+snapshot+"/commands/"+key

def config_sha(d, name):
    if name=="build":
        return sha({"pom_git_blob_sha":"dab45a1d6580ed53ebe67b341312ef588cb80131",
                    "argv":d["snapshots"][1]["commands"]["build"]["argv"]})
    if name=="format_aosp":
        return sha({"formatter_version":d["formatter_version"],
                    "formatter_sha256":d["formatter_sha256"],
                    "formatter_flags":d["formatter_flags"]})
    if name=="javac_lint":
        return sha({"javac_release":"21","lint_flag":"-Xlint:all",
                    "source_tree":d["snapshots"][1]["time_service_tree_oid"]})
    raise ValueError("EX6_UNKNOWN_LINTER_CONFIG")

def baseline(pg05_exit):
    d=observed()
    snapshot=d["snapshots"][0]
    sols=pg05_exit["solutions"]
    rows=[]
    for sol in sols:
        sid=sol["solution_id"]
        for name,kind in (("build","BUILD"),("javac_lint","LINT")):
            v=snapshot["commands"][name]
            rows.append({
                "command_id":"ex6-base-"+kind.lower()+"-"+sid,
                "solution_id":sid,"kind":kind,
                "command_ref":command_ref("baseline",name),
                "command_sha256":sha(v["argv"]),
                "result":"PASS" if v["exit_code"]==0 else "FAIL",
                "exit_code":v["exit_code"],
                "stdout_sha256":v["stdout"]["sha256"],
                "stderr_sha256":v["stderr"]["sha256"],
                "violation_refs":[],
                "execution_receipt_ref":command_ref("baseline",name)+
                    "#jsonsha256="+hashlib.sha256(
                        (Path(__file__).resolve().parents[1]/"evidence"/
                         RECEIPTS[active_label()]["name"]).read_bytes()
                    ).hexdigest(),
            })
    return {
        "schema_version":"PG06_UNCHANGED_TARGET_BASELINE_OBSERVATION_CANDIDATE_V1",
        "target_repo":pg05_exit["target_binding"]["repo_full_name"],
        "base_head_sha":SNAPSHOT_BASE,
        "observation_ref":active_ref()+"#baseline",
        "execution_environment_ref":active_ref()+"#snapshot/baseline",
        "unchanged_target_claim":True,
        "command_results":rows,
    }

def pg08_build(pg07_c6):
    d=observed()
    v=d["snapshots"][1]["commands"]["build"]
    rows=[]
    for row in pg07_c6["batches"]:
        sid=row["solution_id"]
        rows.append({
            "solution_id":sid,"executor_mode":"GPT_NATIVE",
            "executor_result_ref":RUN_REF,
            "candidate_head_sha":row["candidate_head_sha_reported"],
            "diff_sha256":row["diff_sha256_reported"],
            "target_repo":pg07_c6["target_repo"],
            "base_head_sha":pg07_c6["base_head_sha"],
            "commands":[{
                "command_id":"ex6-maven-package-"+sid,
                "command_ref":command_ref("candidate","build"),
                "tool_name":"maven",
                "tool_version":"pom/spring-boot-4.1.1",
                "config_sha256":config_sha(d,"build"),
                "execution_receipt_ref":active_ref()+"#snapshot/candidate-merged-"+active_candidate(),
                "stdout_sha256":v["stdout"]["sha256"],
                "stderr_sha256":v["stderr"]["sha256"],
                "result":"PASS" if v["exit_code"]==0 else "FAIL",
                "exit_code":v["exit_code"],
            }],
        })
    return rows

def pg08_format_lint(pg07_c6):
    d=observed()
    commands=d["snapshots"][1]["commands"]
    format_paths=base64.b64decode(commands["format_aosp"]["stdout"]["base64"]).decode().splitlines()
    rows=[]
    for row in pg07_c6["batches"]:
        sid=row["solution_id"]
        checks=[]
        for kind,name in (("FORMAT","format_aosp"),("LINT","javac_lint")):
            v=commands[name]
            findings=[{
                "violation_ref":active_ref()+"#aosp/"+p,
                "severity":"BLOCK","rule_id":AOSP_RULE,
                "path":p,"line":None,"scope":"DIFF",
            } for p in format_paths] if kind=="FORMAT" else []
            checks.append({
                "kind":kind,"command_id":"ex6-"+kind.lower()+"-"+sid,
                "command_ref":command_ref("candidate",name),
                "tool_name":"google-java-format" if kind=="FORMAT" else "javac",
                "tool_version":"1.30.0 --aosp" if kind=="FORMAT" else "21 -Xlint:all",
                "config_sha256":config_sha(d,name),
                "execution_receipt_ref":active_ref()+"#original-zip-preserved",
                "stdout_sha256":v["stdout"]["sha256"],
                "stderr_sha256":v["stderr"]["sha256"],
                "result":"PASS" if v["exit_code"]==0 else "FAIL",
                "exit_code":v["exit_code"],
                "findings":findings,
            })
        rows.append({
            "solution_id":sid,"executor_mode":"GPT_NATIVE",
            "candidate_head_sha":row["candidate_head_sha_reported"],
            "diff_sha256":row["diff_sha256_reported"],
            "target_repo":pg07_c6["target_repo"],
            "base_head_sha":pg07_c6["base_head_sha"],
            "checks":checks,
        })
    return rows

def rem_d4_process():
    d=observed()
    v=d["snapshots"][1]["commands"]
    return {
        "requirement_id":"REM-D4",
        "kind":"PROCESS",
        "visible_test_ref":command_ref("candidate","visible_ex6"),
        "visible_test_exit_code":v["visible_ex6"]["exit_code"],
        "visible_test_stdout_sha256":v["visible_ex6"]["stdout"]["sha256"],
        "aosp_receipt_ref":command_ref("candidate","format_aosp"),
        "aosp_exit_code":v["format_aosp"]["exit_code"],
        "aosp_stdout_sha256":v["format_aosp"]["stdout"]["sha256"],
        "process_requirement_satisfied":v["visible_ex6"]["exit_code"]==0 and v["format_aosp"]["exit_code"]==0,
        "reason":"VISIBLE_AND_AOSP_PASS" if v["visible_ex6"]["exit_code"]==0 and v["format_aosp"]["exit_code"]==0 else "FORMAT_AOSP_EXIT_1" if v["format_aosp"]["exit_code"]==1 else "FORMAT_OR_VISIBLE_FAILED",
        "production_authority":False,
    }
